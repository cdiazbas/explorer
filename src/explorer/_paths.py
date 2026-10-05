"""Where explorer keeps its own files: one cache directory per user (XDG), never next to the code, so one
install on shared storage (StorNext) works for every user who can read it."""
import os
import shutil
from pathlib import Path

from ._name import APP_NAME


def cache_dir() -> Path:
    """~/.cache/<app> or $XDG_CACHE_HOME/<app>; not created here."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / APP_NAME


def config_dir() -> Path:
    """~/.config/<app> or $XDG_CONFIG_HOME/<app>, on every system (one rule with the cache's); not created here."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / APP_NAME


KEEP_LOGS = 30                                          # sessions of each trace kept: the newest


def trace_log(kind: str) -> Path:
    """logs/<kind>-<pid>.log in the cache, its folder made; the oldest of that kind beyond KEEP_LOGS removed (with a
    folder of the same name, as the bridge's probes keep their images in), so traces on by default stay bounded."""
    d = cache_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    old = sorted(d.glob(f"{kind}-*.log"), key=lambda p: p.stat().st_mtime)
    for p in old[:max(0, len(old) - (KEEP_LOGS - 1))]:
        try:
            p.unlink()
            if p.with_suffix("").is_dir():
                shutil.rmtree(p.with_suffix(""), ignore_errors=True)
        except OSError:
            pass                                        # another session's, in use or gone: left
    return d / f"{kind}-{os.getpid()}.log"
