"""Decisions taken from measurements on this machine, not from the operating system's name.

StorageProbe  ~0.1-0.5 s at start-up: the filesystem type and a few timed small reads decide the strip width,
              how many images to read ahead and how many threads the scattered reads use. Behaviour depends on
              the storage (local SSD ~0.1 ms per small read; StorNext 7-15 ms on Linux and macOS alike), not on
              the OS (docs/measured.md).
MemoryGuard   the caches' budget from the memory actually available, re-checked about once a second. macOS swaps
              other applications before "available" reacts, so there the budget is small and halves as soon as
              swap grows; on Linux the cgroup limit and MemAvailable are honoured, with a hard cap.
plan_budgets  how a budget splits between the image cache and the per-pixel blocks.
Ported from the prototype's app/policy.py and Viewer._memory.
"""
import os
import subprocess
import sys
import time
from dataclasses import dataclass

import numpy as np

from . import sysmem


def mount_of(path) -> dict:
    """Mount point and filesystem type of path (df and mount; empty on failure)."""
    info: dict = {}
    try:
        mp = subprocess.run(["df", "-P", path], capture_output=True, text=True, timeout=5).stdout.splitlines()[-1]
        info["mount_point"] = mp = mp.split()[-1]
        for line in subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout.splitlines():
            if f" on {mp} " in line:
                info["fstype"] = (line.split(" type ")[1].split()[0] if " type " in line
                                  else line.split("(")[-1].split(",")[0].strip(")"))
    except (OSError, subprocess.SubprocessError, IndexError) as e:
        info["error"] = str(e)
    return info


class StorageProbe:
    NETWORK_FS = {"cvfs", "acfs", "nfs", "nfs4", "smbfs", "cifs", "afpfs", "lustre", "gpfs", "beegfs"}

    def __init__(self, frames, n_small: int = 8, seed: int = 0):
        """frames: an explorer.data.io.FrameReader of the cube to be read."""
        t0 = time.perf_counter()
        self.mount = mount_of(os.path.realpath(frames.layout.path))
        rng = np.random.default_rng(seed)
        it, nfr = frames.layout.dtype.itemsize, int(np.prod(frames.shape[:-2]))
        small = []
        for _ in range(n_small):
            k, y, x = rng.integers(nfr), rng.integers(frames.ny), rng.integers(frames.nx)
            q = time.perf_counter()
            at = frames.layout.offset + int(k) * frames.frame_bytes + (int(y) * frames.nx + int(x)) * it
            os.pread(frames.fd, it, at)
            small.append((time.perf_counter() - q) * 1e3)
        self.small_ms = float(np.median(small))
        self.probe_ms = (time.perf_counter() - t0) * 1e3
        self.decide(self.mount.get("fstype", ""), self.small_ms)

    def decide(self, fstype: str, small_ms: float) -> None:
        """Network storage: requests are expensive and bytes cheap for small reads, so wide strips, more images
        ahead and many threads for scattered reads: a cold lambda-t of 6173 read a row per frame with 32/64/128
        threads, 1.00/0.56/0.42 (bellatrix, 2026-09-29; the prototype's 64 came from 4-byte reads,
        4735/1757/1058/406-573/310/282 ms with 4/8/16/32/48/64). Local SSD: 16 threads (40/22/15/14 ms with
        4/8/16/32 on the Mac)."""
        self.fstype = fstype
        self.network = fstype in self.NETWORK_FS or small_ms > 1.0
        if self.network:
            self.strip, self.read_ahead, self.readers, self.gather_threads = 32, 4, 4, 128
        else:
            self.strip, self.read_ahead, self.readers, self.gather_threads = 8, 2, 2, 16

    def describe(self) -> str:
        kind = "network" if self.network else "local"
        return (f"{self.fstype or '?'} ({kind}), small read {self.small_ms:.2f} ms; "
                f"strip {self.strip} px, read-ahead {self.read_ahead}")


class MemoryGuard:
    """Budget in bytes for the caches; call update() about once a second."""

    MAC_FRAC, MAC_CAP = 0.15, 2 << 30
    LINUX_FRAC, LINUX_CAP = 0.25, 8 << 30
    SWAP_STEP = 256 << 20            # macOS: halve the budget each time swap grows by this
    FLOOR = 128 << 20

    def __init__(self, snapshot=sysmem.snapshot, mac: bool | None = None):
        self.snapshot = snapshot
        self.mac = sys.platform == "darwin" if mac is None else mac
        s = snapshot()
        self.swap0 = s.get("swap_used") or 0
        frac, cap = (self.MAC_FRAC, self.MAC_CAP) if self.mac else (self.LINUX_FRAC, self.LINUX_CAP)
        self.budget = max(256 << 20, sysmem.budget(frac, cap, s=s))
        self.start_budget = self.budget
        self.last = s
        self.events: list = []

    def update(self) -> int:
        s = self.snapshot()
        self.last = s
        if self.mac:
            grown = (s.get("swap_used") or 0) - self.swap0
            level = s.get("pressure")
            if grown > self.SWAP_STEP or (level is not None and level < 25):
                self.budget = max(self.FLOOR, self.budget // 2)
                self.swap0 = s.get("swap_used") or 0
                self.events.append((time.time(), "shrink", self.budget, grown, level))
        else:
            self.budget = min(self.budget, max(self.FLOOR, sysmem.budget(self.LINUX_FRAC, self.LINUX_CAP, s=s)))
        return self.budget

    def room(self) -> int:
        """Bytes the machine has free for this process now (last snapshot; cgroup limits included)."""
        return sysmem.room(self.last)

    def describe(self) -> str:
        return f"cache budget {self.budget / 2**30:.2f} GB" + (f" (shrunk {len(self.events)}x)" if self.events else "")


@dataclass(frozen=True)
class Budgets:
    images: int                      # bytes for the image cache
    pixel: int                       # bytes for the per-pixel blocks
    whole_loop: bool                 # the images of one whole t loop fit


IMG_BASE = 512 << 20                 # images kept when a whole loop does not fit
LOOP_FRAC = 0.10                     # a whole loop only within this share of the free memory
PIXEL_SHARE = 0.3


def plan_budgets(budget: int, room: int, frame_bytes: int, nt: int, read_ahead: int) -> Budgets:
    """Split a budget. The image cache holds one whole loop (every t at the current lambda and Stokes, plus the
    frames read ahead) when it fits in LOOP_FRAC of the free memory and within the budget; else IMG_BASE. Only a
    whole loop speeds a repeat up: 16.5 against 18.4-19.8 ms per frame with 0.25-2 GB that did not hold it
    (bellatrix, 6173 cube). The per-pixel blocks get PIXEL_SHARE of the budget."""
    loop = frame_bytes * (max(1, nt) + max(0, read_ahead))
    whole = loop <= min(LOOP_FRAC * room, budget)
    return Budgets(images=loop if whole else min(IMG_BASE, int(budget * 0.9)), pixel=int(budget * PIXEL_SHARE),
                   whole_loop=whole)
