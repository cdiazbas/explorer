"""Whether a file's bytes are on this disk, from its metadata alone (os.stat: nothing is read, so nothing is brought
back). A hierarchical store (StorNext, for one) moves old files to tape and leaves them on disk with their size and
almost no blocks; the first read then waits until the store brings the file back, minutes for tens of GB.

A sparse file (holes never written) looks the same: an SST cube is written whole, so its blocks cover its size.
"""
import os

MIN_BYTES = 64 << 20        # a smaller file comes back in moments: nothing said
ON_DISK = 0.5               # under this fraction of its bytes on disk, a file is said to be away


def on_disk(path) -> float | None:
    """The fraction of path's bytes with blocks on the disk (st_blocks of 512 bytes over st_size), at most 1; None
    where the system gives no st_blocks, the file is empty, or it cannot be stat'ed."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    blocks = getattr(st, "st_blocks", None)
    if blocks is None or st.st_size <= 0:
        return None
    return min(1.0, blocks * 512 / st.st_size)


def away(paths) -> list[str]:
    """The files of paths of MIN_BYTES or more with less than ON_DISK of them on disk, each once."""
    out: list[str] = []
    for p in dict.fromkeys(str(p) for p in paths if p):
        f = on_disk(p)
        try:
            size = os.stat(p).st_size
        except OSError:
            continue
        if f is not None and f < ON_DISK and size >= MIN_BYTES:
            out.append(p)
    return out


def away_text(path) -> str:
    """One line for a file that is away: its name, its size, how much of it is on disk, and why the wait."""
    size = os.stat(path).st_size
    f = on_disk(path) or 0.0
    return (f"{os.path.basename(path)}: {size / 1e9:.1f} GB, {100 * f:.0f} % of it on disk: probably on tape "
            f"(a hierarchical store such as StorNext); its first read waits until it is brought back, minutes for "
            f"tens of GB")


def on_disk_bytes(paths) -> float:
    """The bytes of paths with blocks on the disk, together: grows while a file comes back from tape."""
    total = 0.0
    for p in paths:
        try:
            total += (on_disk(p) or 0.0) * os.stat(p).st_size
        except OSError:
            continue
    return total


def on_disk_gb(paths) -> str:
    """How much of each file is on disk now, "name 12.3 of 91.9 GB on disk", joined: whether a file coming back from
    tape is getting nearer."""
    parts = []
    for p in paths:
        try:
            size = os.stat(p).st_size
        except OSError:
            continue
        parts.append(f"{os.path.basename(p)} {(on_disk(p) or 0.0) * size / 1e9:.1f} of {size / 1e9:.1f} GB on disk")
    return "; ".join(parts)
