"""How much memory explorer may use on this machine: the same answer on Linux and macOS, standard library only.

snapshot() returns bytes:
  total       physical memory
  available   what can be allocated without swapping (Linux: MemAvailable, which counts reclaimable page cache;
              macOS: free + inactive + purgeable pages)
  swap_used   swap in use (a rising value while a cache fills means the cache is too greedy)
  limit       the tightest cgroup memory limit on this process (Linux: v2's memory.max of its node or an
              ancestor, v1's memory.limit_in_bytes) or None: a scope, job or container limit is tighter than the
              machine's memory and must win
  cg_used     that cgroup's memory in use (Linux) or None
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
# interface thread they were the only frames over 17 ms during playback; through ctypes 0.011 ms, same values.
# The command version stays as the fallback.


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


CGROUP_ROOT = "/sys/fs/cgroup"
PROC_CGROUP = "/proc/self/cgroup"
V1_UNLIMITED = 1 << 60      # cgroup v1 writes "no limit" as a number near 2**63


def _cgroup_memory():
    """(limit, used, leaf) of the tightest memory limit on this process: cgroup v2's memory.max and memory.current
    from its own node up (a limit on an ancestor, systemd's user-UID.slice, binds it as well), and v1's memory
    controller (memory.limit_in_bytes, usage_in_bytes); the tightest is the one with the least room left. leaf: v2's
    own node, for its pressure. (None, None, leaf) without a limit."""
    try:
        lines = open(PROC_CGROUP).read().splitlines()
    except OSError:
        return None, None, None
    root = CGROUP_ROOT.rstrip("/")
    best, leaf = None, None
    for line in lines:
        hid, _, rest = line.partition(":")
        ctrls, _, path = rest.partition(":")
        if hid == "0" and ctrls == "":                  # v2: the node and each ancestor up to the root
            leaf = (root + path).rstrip("/") or root
            d = leaf
            while True:
                m, c = _read(d + "/memory.max"), _read(d + "/memory.current")
                if m and m != "max" and c and c.isdigit():
                    best = min(best or (1 << 62, 0, 0), (int(m) - int(c), int(m), int(c)))
                if d == root or not d.startswith(root):
                    break
                d = d.rsplit("/", 1)[0] or root
        elif "memory" in ctrls.split(","):             # v1: the memory controller's own hierarchy
            d = f"{root}/memory{path}".rstrip("/")
            m, c = _read(d + "/memory.limit_in_bytes"), _read(d + "/memory.usage_in_bytes")
            if m and c and m.isdigit() and c.isdigit() and int(m) < V1_UNLIMITED:
                best = min(best or (1 << 62, 0, 0), (int(m) - int(c), int(m), int(c)))
    if best is None:
        return None, None, leaf
    return best[1], best[2], leaf


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
    limit, cg_used, cg = _cgroup_memory()
    pressure = _psi("/proc/pressure/memory")
    if cg:
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
