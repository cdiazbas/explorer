"""Logging: one logger per layer under the application's root logger, a console at WARNING and a rotating file
at INFO in ~/.cache/explorer/logs/ (over ssh -Y the terminal may not be in view).

Per-layer detail without flooding the rest: EXPLORER_LOG="data.io=DEBUG,core=INFO" (a bare level, e.g. "DEBUG",
applies to everything). Never log per frame or per cursor move at INFO: the terminal costs too, over ssh; what
repeats goes to spans (obs/spans.py), not to the log.
"""
import logging
import logging.handlers
import os
import sys

from .._name import APP_NAME, ENV_PREFIX
from .._paths import cache_dir

_FMT = "%(asctime)s %(levelname)s %(name)s [%(threadName)s]: %(message)s"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """The logger of one layer or module, e.g. get_logger("data.io") -> "explorer.data.io"."""
    return logging.getLogger(f"{APP_NAME}.{name}" if name else APP_NAME)


def parse_spec(spec: str) -> dict:
    """"data.io=DEBUG,core=INFO" -> {"data.io": DEBUG, "core": INFO}; a bare level is for "" (everything)."""
    out = {}
    for part in filter(None, (p.strip() for p in (spec or "").split(","))):
        name, _, level = part.rpartition("=")
        lvl = logging.getLevelName(level.strip().upper())
        if not isinstance(lvl, int):
            raise ValueError(f"unknown log level {level!r} in {spec!r}")
        out[name.strip()] = lvl
    return out


class _LayerFilter(logging.Filter):
    """Per output: its own level for every layer, except the layers named in EXPLORER_LOG, which get theirs.
    (Handler levels alone cannot do this: lowering one for data.io would let every layer's DEBUG through.)"""

    def __init__(self, default: int, levels: dict):
        super().__init__()
        self.default = default
        self.levels = sorted(((f"{APP_NAME}.{k}", v) for k, v in levels.items()), key=lambda kv: -len(kv[0]))

    def filter(self, record):
        for prefix, lvl in self.levels:                 # the most specific layer that matches decides
            if record.name == prefix or record.name.startswith(prefix + "."):
                return record.levelno >= lvl
        return record.levelno >= self.default


def setup(console_level=logging.WARNING, file_level=logging.INFO, spec: str | None = None, to_file=True):
    """Configure the application's loggers once; calling it again replaces the previous configuration."""
    global _configured
    root = logging.getLogger(APP_NAME)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    for lg in list(logging.Logger.manager.loggerDict.values()):     # forget levels from a previous setup()
        if isinstance(lg, logging.Logger) and lg.name.startswith(APP_NAME + "."):
            lg.setLevel(logging.NOTSET)
    root.propagate = False
    levels = parse_spec(spec) if spec else {}
    if "" in levels:                                    # a bare level: the console's level for everything
        console_level = levels.pop("")
    con = logging.StreamHandler(sys.stderr)
    con.addFilter(_LayerFilter(console_level, levels))
    con.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(con)
    lowest = console_level
    if to_file:
        try:
            d = cache_dir() / "logs"
            d.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(d / f"{APP_NAME}.log", maxBytes=2 << 20, backupCount=5,
                                                      encoding="utf-8")
            fh.addFilter(_LayerFilter(min(file_level, console_level), levels))
            fh.setFormatter(logging.Formatter(_FMT))
            root.addHandler(fh)
            lowest = min(lowest, file_level)
        except OSError as e:                        # a read-only home must not stop the application
            root.warning("no log file (%s): logging to the console only", e)
    root.setLevel(lowest)                               # records below every output's level are not even built
    for name, lvl in levels.items():                    # named layers may go below it
        get_logger(name).setLevel(lvl)
    _configured = True
    return root


def setup_from_env():
    """setup() from EXPLORER_LOG, once per process (the command calls it before any subcommand)."""
    if not _configured:
        setup(spec=os.environ.get(ENV_PREFIX + "LOG"))
