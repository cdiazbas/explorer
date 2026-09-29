"""How much memory explorer may use on this machine: the same answer on Linux and macOS, standard library only.

snapshot() returns bytes:
  total       physical memory
  available   what can be allocated without swapping (Linux: MemAvailable, which counts reclaimable page cache;
              macOS: free + inactive + purgeable pages)
  swap_used   swap in use (a rising value while a cache fills means the cache is too greedy)
  limit       cgroup memory.max of this process (Linux) or None: a scope or container limit is tighter than the
              machine's memory and must win
  cg_used     cgroup memory.current (Linux) or None
  pressure    macOS kern.memorystatus_level (% of memory the kernel counts as free); Linux PSI "some avg10" of the
              cgroup or machine (% of time stalled on memory); None if absent
budget(frac, cap) = what a cache may take: frac of the room left, never more than cap.
Ported from the prototype's bench/membench/sysmem.py.
"""
import ctypes
import ctypes.util
import subprocess
import sys
import time

_mac = sys.platform == "darwin"


def _sysctl(name):
    return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True).stdout.strip()


def _mac_snapshot_cmd():
    total = int(_sysctl("hw.memsize"))
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout.splitlines()
    page = int(out[0].split("page size of")[1].split()[0])
    pages = {}
    for line in out[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                pages[k.strip().strip('"')] = int(v.strip().rstrip("."))
            except ValueError:
                pass
    avail = sum(pages.get(k, 0) for k in ("Pages free", "Pages inactive", "Pages purgeable",
                                          "Pages speculative")) * page
    su = _sysctl("vm.swapusage")                      # "total = 2048.00M  used = 1034.25M ..."
    used = su.split("used =")[1].split()[0] if "used =" in su else "0M"
    mult = {"K": 1 << 10, "M": 1 << 20, "G": 1 << 30}[used[-1]]
    lvl = _sysctl("kern.memorystatus_level")
    return dict(total=total, available=avail, swap_used=int(float(used[:-1]) * mult),
                limit=None, cg_used=None, pressure=float(lvl) if lvl else None)


# The same numbers without subprocesses: four sysctl/vm_stat processes cost 14-34 ms, called once a second on the
# interface thread they were the only frames over 17 ms during playback; through ctypes 0.011 ms, same values
# (docs/measured.md). The command version stays as the fallback.


class _XswUsage(ctypes.Structure):                     # <sys/sysctl.h> struct xsw_usage
    _fields_ = [("total", ctypes.c_uint64), ("avail", ctypes.c_uint64), ("used", ctypes.c_uint64),
                ("pagesize", ctypes.c_uint32), ("encrypted", ctypes.c_bool)]


class _VmStat64(ctypes.Structure):                     # <mach/vm_statistics.h> struct vm_statistics64
    _fields_ = [(n, ctypes.c_uint32) for n in ("free_count", "active_count", "inactive_count", "wire_count")] + \
               [(n, ctypes.c_uint64) for n in ("zero_fill_count", "reactivations", "pageins", "pageouts", "faults",
                                               "cow_faults", "lookups", "hits", "purges")] + \
               [(n, ctypes.c_uint32) for n in ("purgeable_count", "speculative_count")] + \
               [(n, ctypes.c_uint64) for n in ("decompressions", "compressions", "swapins", "swapouts")] + \
               [(n, ctypes.c_uint32) for n in ("compressor_page_count", "throttled_count", "external_page_count",
                                               "internal_page_count")] + \
               [("total_uncompressed_pages_in_compressor", ctypes.c_uint64)]


_libc = None


def _mac_libc():
    global _libc
    if _libc is None:
        c = ctypes.CDLL(ctypes.util.find_library("c"))
        c.sysctlbyname.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                   ctypes.c_void_p, ctypes.c_size_t]
        c.mach_host_self.restype = ctypes.c_uint32
        c.host_statistics64.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        _libc = c
    return _libc


def _sysctl_c(name, ctype):
    v, n = ctype(), ctypes.c_size_t(ctypes.sizeof(ctype))
    if _mac_libc().sysctlbyname(name.encode(), ctypes.byref(v), ctypes.byref(n), None, 0):
        raise OSError(f"sysctlbyname({name}) failed")
    return v


def _mac_snapshot():
    try:
        c = _mac_libc()
        total = _sysctl_c("hw.memsize", ctypes.c_uint64).value
        page = _sysctl_c("hw.pagesize", ctypes.c_int64).value
        vm, cnt = _VmStat64(), ctypes.c_uint32(ctypes.sizeof(_VmStat64) // 4)
        if c.host_statistics64(c.mach_host_self(), 4, ctypes.byref(vm), ctypes.byref(cnt)):   # HOST_VM_INFO64
            raise OSError("host_statistics64 failed")
        sw = _sysctl_c("vm.swapusage", _XswUsage)
        try:
            lvl = float(_sysctl_c("kern.memorystatus_level", ctypes.c_int).value)
        except OSError:
            lvl = None
    except (OSError, AttributeError):
        return _mac_snapshot_cmd()
    # vm_stat's "Pages free" is free_count - speculative_count, so its free + inactive + purgeable +
    # speculative (what _mac_snapshot_cmd adds up) is free_count + inactive_count + purgeable_count
    avail = (vm.free_count + vm.inactive_count + vm.purgeable_count) * page
    return dict(total=total, available=avail, swap_used=int(sw.used), limit=None, cg_used=None, pressure=lvl)


def _cgroup_dir():
    try:
        for line in open("/proc/self/cgroup"):
            if line.startswith("0::"):
                return "/sys/fs/cgroup" + line.strip()[3:]
    except OSError:
        pass
    return None


def _read(path):
    try:
        return open(path).read().strip()
    except OSError:
        return None


def _psi(path):
    s = _read(path)
    if not s:
        return None
    return float(s.splitlines()[0].split("avg10=")[1].split()[0])


def _linux_snapshot():
    mi = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":")
        mi[k] = int(v.split()[0]) * 1024
    cg = _cgroup_dir()
    limit = cg_used = None
    pressure = _psi("/proc/pressure/memory")
    if cg:
        m = _read(cg + "/memory.max")
        if m and m != "max":
            limit = int(m)
        c = _read(cg + "/memory.current")
        cg_used = int(c) if c else None
        p = _psi(cg + "/memory.pressure")
        if p is not None:
            pressure = p
    return dict(total=mi["MemTotal"], available=mi["MemAvailable"],
                swap_used=mi["SwapTotal"] - mi["SwapFree"], limit=limit, cg_used=cg_used,
                pressure=pressure)


def snapshot():
    s = _mac_snapshot() if _mac else _linux_snapshot()
    s["t"] = time.time()
    return s


def room(s=None):
    """Bytes this process could still take: machine availability, clipped by its cgroup."""
    s = s or snapshot()
    r = s["available"]
    if s["limit"] is not None and s["cg_used"] is not None:
        r = min(r, s["limit"] - s["cg_used"])
    return max(r, 0)


def budget(frac=0.5, cap=None, s=None):
    b = int(frac * room(s))
    return min(b, cap) if cap else b
