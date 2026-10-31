"""Storage probe, memory guard, budget split and the frame cache, with simulated snapshots where the machine
would otherwise decide the outcome."""
import sys
import threading

import numpy as np
import pytest

from explorer.data import formats, sysmem
from explorer.data.cache import FrameCache
from explorer.data.io import FrameReader
from explorer.data.policy import IMG_BASE, MemoryGuard, StorageProbe, plan_budgets
from explorer.testing import synth

GB = 1 << 30


@pytest.fixture
def reader(tmp_path):
    p = synth.write_dataset(tmp_path, "c", shape=(4, 1, 3, 16, 12), sp=False, icube=False)["im"]
    with FrameReader(formats.open_layout(p)) as r:
        yield r


def test_snapshot_is_sane_on_this_machine():
    s = sysmem.snapshot()
    assert s["total"] > 0 and 0 <= s["available"] <= s["total"] and s["swap_used"] >= 0
    assert 0 <= sysmem.room(s) <= s["available"]
    assert sysmem.budget(0.5, cap=1 << 20, s=s) <= 1 << 20


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS readers")
def test_ctypes_and_commands_agree_on_macos():
    fast, slow = sysmem._mac_snapshot(), sysmem._mac_snapshot_cmd()
    assert fast["total"] == slow["total"]
    assert abs(fast["swap_used"] - slow["swap_used"]) < 64 << 20       # swap may move between the two calls


def test_room_is_clipped_by_the_cgroup():
    s = dict(total=64 * GB, available=40 * GB, swap_used=0, limit=10 * GB, cg_used=7 * GB, pressure=None)
    assert sysmem.room(s) == 3 * GB


def test_probe_decides_by_storage(reader):
    p = StorageProbe(reader)
    assert p.small_ms >= 0 and p.strip in (8, 32)
    p.decide("cvfs", 0.05)                               # StorNext, even with a fast read
    assert (p.network, p.strip, p.read_ahead, p.gather_threads) == (True, 32, 4, 128)
    p.decide("apfs", 5.0)                                # a local type that answers like a network one
    assert p.network and p.strip == 32
    p.decide("apfs", 0.1)
    assert (p.network, p.strip, p.read_ahead, p.gather_threads) == (False, 8, 2, 16)


class _Snaps:
    def __init__(self, **first):
        self.s = dict(total=32 * GB, available=8 * GB, swap_used=4 * GB, limit=None, cg_used=None, pressure=60.0)
        self.s.update(first)

    def __call__(self):
        return dict(self.s)


def test_guard_on_macos_halves_when_swap_grows_or_pressure_drops():
    snaps = _Snaps()
    g = MemoryGuard(snaps, mac=True)
    assert g.budget == int(0.15 * 8 * GB)
    snaps.s["swap_used"] += 300 << 20                     # more than SWAP_STEP
    assert g.update() == int(0.15 * 8 * GB) // 2
    snaps.s["pressure"] = 20.0
    assert g.update() == int(0.15 * 8 * GB) // 4
    for _ in range(10):
        g.update()
    assert g.budget == MemoryGuard.FLOOR


def test_guard_on_linux_never_grows_and_honours_the_cgroup():
    snaps = _Snaps(available=40 * GB, pressure=None)
    g = MemoryGuard(snaps, mac=False)
    assert g.budget == 8 * GB                             # 25 % of 40 GB, capped at 8 GB
    snaps.s.update(limit=6 * GB, cg_used=2 * GB)          # a cgroup leaves 4 GB
    assert g.update() == GB
    snaps.s.update(limit=None, cg_used=None)
    assert g.update() == GB                               # does not grow back


def test_linked_cubes_share_one_budget():
    """Linked cubes (ROADMAP E8.1): each its 1/n of the one budget, following it as it shrinks; each cube with a
    guard of its own held n budgets."""
    from explorer.data.policy import GuardShare

    snaps = _Snaps()
    g = MemoryGuard(snaps, mac=True)
    a, b = GuardShare(g, 2), GuardShare(g, 2)
    print("alone", g.budget, "each of two", a.budget, a.describe())
    assert a.budget + b.budget <= g.budget and a.budget == g.budget // 2 and a.room() == g.room() // 2
    snaps.s["swap_used"] += 300 << 20
    assert a.update() == g.budget // 2 == int(0.15 * 8 * GB) // 4


def test_budget_split():
    frame = 16 << 20
    whole = plan_budgets(budget=4 * GB, room=40 * GB, frame_bytes=frame, nt=186, read_ahead=4)
    assert whole.whole_loop and whole.images == frame * 190 and whole.pixel == int(4 * GB * 0.3)
    small = plan_budgets(budget=GB, room=8 * GB, frame_bytes=frame, nt=186, read_ahead=4)
    assert not small.whole_loop and small.images == min(IMG_BASE, int(GB * 0.9))


def test_frame_cache_budget_and_prefetch(reader, monkeypatch):
    c = FrameCache(reader, max_bytes=2 * reader.ny * reader.nx * 4)
    np.testing.assert_array_equal(c.get((0, 0, 1)), reader.read((0, 0, 1)))
    c.get((1, 0, 1))
    c.get((2, 0, 1))
    assert c.nbytes() == 2 * c.frame_nbytes                # the oldest frame was dropped
    reads = []
    real_read = reader.read
    monkeypatch.setattr(reader, "read", lambda idx, chunks=None: (reads.append(idx), real_read(idx, chunks))[1])
    c.prefetch((3, 0, 0))
    c.reader.pool.submit(lambda: None).result()           # let the pool finish the read ahead
    done = threading.Event()
    c.reader.pool.submit(done.set)
    done.wait(5)
    c.get((3, 0, 0))
    assert reads == [(3, 0, 0)]                            # get() used the frame read ahead


def test_a_failed_read_ahead_is_forgotten(reader, monkeypatch):
    c = FrameCache(reader)
    real_read = reader.read
    calls = []

    def flaky(idx, chunks=None):
        calls.append(idx)
        if len(calls) == 1:
            raise OSError("network hiccup")
        return real_read(idx, chunks)

    monkeypatch.setattr(reader, "read", flaky)
    c.prefetch((1, 0, 0))
    for _ in range(3):
        c.reader.pool.submit(lambda: None).result()
    np.testing.assert_array_equal(c.get((1, 0, 0)), real_read((1, 0, 0)))
    assert len(calls) == 2                                 # read again, not a cached failure



@pytest.mark.parametrize("tree", ["v2 leaf", "v2 ancestor", "v1", "none"])
def test_the_tightest_cgroup_memory_limit_is_honoured_wherever_it_is_set(tmp_path, monkeypatch, tree):
    """Only the process's own cgroup v2 node was read: a limit on an ancestor (systemd's user-UID.slice on a shared
    login node: the leaf says "max") or under cgroup v1 (RHEL 7/8, many compute nodes: no 0:: line) was not seen, the
    budget came from the machine's memory and the caches could grow past the job's limit to an OOM kill. The tightest
    limit from the leaf up, v1's memory controller too, is the one that counts, with its own usage."""
    from explorer.data import sysmem

    root = tmp_path / "cgroup"
    G = 1 << 30
    if tree.startswith("v2"):
        leaf = root / "user.slice" / "user-1.slice" / "session-1.scope"
        leaf.mkdir(parents=True)
        (leaf / "memory.max").write_text("max\n" if tree == "v2 ancestor" else f"{8 * G}\n")
        (leaf / "memory.current").write_text(f"{1 * G}\n")
        (leaf.parent / "memory.max").write_text(f"{4 * G}\n" if tree == "v2 ancestor" else "max\n")
        (leaf.parent / "memory.current").write_text(f"{3 * G}\n")
        (leaf.parent.parent / "memory.max").write_text("max\n")
        proc = "0::/user.slice/user-1.slice/session-1.scope\n"
        want = (4 * G, 3 * G) if tree == "v2 ancestor" else (8 * G, 1 * G)
    elif tree == "v1":
        mem = root / "memory" / "slurm" / "job_7"
        mem.mkdir(parents=True)
        (mem / "memory.limit_in_bytes").write_text(f"{2 * G}\n")
        (mem / "memory.usage_in_bytes").write_text(f"{G // 2}\n")
        proc = "12:pids:/slurm/job_7\n4:memory:/slurm/job_7\n1:name=systemd:/slurm/job_7\n"
        want = (2 * G, G // 2)
    else:
        (root / "user.slice").mkdir(parents=True)
        (root / "user.slice" / "memory.max").write_text("max\n")
        proc = "0::/user.slice\n"
        want = (None, None)
    (tmp_path / "self_cgroup").write_text(proc)
    monkeypatch.setattr(sysmem, "CGROUP_ROOT", str(root), raising=False)
    monkeypatch.setattr(sysmem, "PROC_CGROUP", str(tmp_path / "self_cgroup"), raising=False)
    limit, used = sysmem._cgroup_memory()[:2]
    assert (limit, used) == want
