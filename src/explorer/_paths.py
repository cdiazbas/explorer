"""Where explorer keeps its own files: one cache directory per user (XDG), never next to the code, so one
install on shared storage (StorNext) works for every user who can read it."""
import os
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
