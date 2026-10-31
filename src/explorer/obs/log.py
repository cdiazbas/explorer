"""Logging: one logger per layer under the application's root logger, a console at WARNING and a rotating file
at INFO in ~/.cache/explorer/logs/ (over ssh -Y the terminal may not be in view). The console's lines look like the
person's (obs.say: "12:08:31 WARN  data.io: message"), and the file keeps the person's lines too.

Per-layer detail without flooding the rest: EXPLORER_LOG="data.io=DEBUG,core=INFO" (a bare level, e.g. "DEBUG",
applies to everything). Never log per frame or per cursor move at INFO: the terminal costs too, over ssh; what
repeats goes to spans (obs/spans.py), not to the log.
"""
import logging
import logging.handlers
import os

from .._name import APP_NAME, ENV_PREFIX
from .._paths import cache_dir
from . import say

_FMT = "%(asctime)s %(process)d %(levelname)s %(name)s [%(threadName)s]: %(message)s"   # the process: sessions at once
LOG_BYTES, LOG_KEPT = 2 << 20, 5                        # the log is rotated past this size, at a start, these kept


def _rotated(path) -> None:
    """explorer.log moved to .1 (and on, LOG_KEPT kept) when past LOG_BYTES, before a session opens it: sessions at
    once share the file in append mode, and one never rotates it while another writes (a rotation by size renamed it
    under them, which went on writing into .1, clobbered at the next)."""
    try:
        if os.path.getsize(path) < LOG_BYTES:
            return
        for k in range(LOG_KEPT - 1, 0, -1):
            src = f"{path}.{k}"
            if os.path.exists(src):
                os.replace(src, f"{path}.{k + 1}")
        os.replace(path, f"{path}.1")
    except OSError:                                     # not there yet, or another session rotating it now
        pass


class _LogFile(logging.FileHandler):
    """The log file, in append mode. A write that fails (a full disk, a home over its quota) is said once on the
    terminal and the file left alone from then on: logging's own handleError printed a traceback at every record,
    burying the user's lines under them."""

    def handleError(self, record) -> None:
        if self.level > logging.CRITICAL:
            return
        self.setLevel(logging.CRITICAL + 1)
        import sys

        try:
            err = sys.exc_info()[1]
            sys.stderr.write(f"{APP_NAME}: the log file {self.baseFilename} cannot be written ({err}): "
                             "logging to the terminal only\n")
        except (OSError, ValueError, AttributeError):
            pass
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
    told = say.logger()                                 # the person's lines: their own terminal handler, and the file;
    told.setLevel(logging.INFO)                         # INFO whatever the loop above and the console's level
    for h in [h for h in told.handlers if not isinstance(h, say.Terminal)]:
        told.removeHandler(h)
    levels = parse_spec(spec) if spec else {}
    if "" in levels:                                    # a bare level: the console's level for everything
        console_level = levels.pop("")
    con = say.Terminal(named=True)
    con.addFilter(_LayerFilter(console_level, levels))
    root.addHandler(con)
    lowest = console_level
    if to_file:
        try:
            d = cache_dir() / "logs"
            d.mkdir(parents=True, exist_ok=True)
            _rotated(d / f"{APP_NAME}.log")
            fh = _LogFile(d / f"{APP_NAME}.log", mode="a", encoding="utf-8")
            fh.addFilter(_LayerFilter(min(file_level, console_level), levels))
            fh.setFormatter(logging.Formatter(_FMT))
            root.addHandler(fh)
            told.addHandler(fh)
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
