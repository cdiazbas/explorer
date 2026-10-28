"""What explorer tells the person at the terminal, one line per event: "12:08:31 INFO  message", WARN or ERROR in its
place, the level in colour when the output is a terminal (never with NO_COLOR set, nor on a "dumb" one); a message's
later lines under its first, past the time and the level. Through the logger explorer.say, so that the log file
(obs.log.setup) keeps them with the rest. Never one per frame or per cursor move: what repeats goes to obs.spans.
Standard library only."""
import logging
import os
import sys
import time

from .._name import APP_NAME

NAME = f"{APP_NAME}.say"
LEVELS = {logging.DEBUG: "DEBUG", logging.INFO: "INFO", logging.WARNING: "WARN", logging.ERROR: "ERROR",
          logging.CRITICAL: "ERROR"}
COLOURS = {logging.INFO: "\033[36m", logging.WARNING: "\033[33m", logging.ERROR: "\033[31m",
           logging.CRITICAL: "\033[31m"}               # cyan, yellow, red
RESET = "\033[0m"
INDENT = " " * len("12:08:31 ERROR ")                   # a message's later lines, under its first


def coloured(stream) -> bool:
    """Whether stream takes colour: a terminal, without NO_COLOR (no-color.org) and not TERM=dumb."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):                # no isatty, or a closed stream
        return False


def line(level: int, msg: str, when: float | None = None, colour: bool = False) -> str:
    """The text of one message: "HH:MM:SS LEVEL message", its level padded to five, later lines indented under it."""
    stamp = time.strftime("%H:%M:%S", time.localtime(when))
    tag = f"{LEVELS.get(level, logging.getLevelName(level)):<5}"
    if colour and level in COLOURS:
        tag = f"{COLOURS[level]}{tag}{RESET}"
    first, *rest = str(msg).split("\n")
    return "\n".join([f"{stamp} {tag} {first}", *(INDENT + r for r in rest)])


class Terminal(logging.Handler):
    """Lines on stderr as line() writes them; stderr as it is when a line is written (a test's capture replaces it),
    never the one there was at creation. named: the record's layer before the message ("data.io: ..."), for the
    developers' loggers; the person's (explorer.say) go without."""

    def __init__(self, named: bool = False):
        super().__init__()
        self.named = named

    def emit(self, record) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
            if self.named:
                layer = record.name.removeprefix(APP_NAME + ".")
                msg = f"{layer}: {msg}" if layer and layer != APP_NAME else msg
            stream = sys.stderr
            stream.write(line(record.levelno, msg, record.created, coloured(stream)) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


def logger() -> logging.Logger:
    """explorer.say, with its terminal line at INFO the first time it is asked for (obs.log.setup adds the file)."""
    lg = logging.getLogger(NAME)
    if not any(isinstance(h, Terminal) for h in lg.handlers):
        lg.addHandler(Terminal())
        lg.propagate = False                            # not again through the developers' console
    if lg.level != logging.INFO:                        # its own: never the console's WARNING through its parent
        lg.setLevel(logging.INFO)
    return lg


def info(msg: str) -> None:
    logger().info(msg)


def warn(msg: str) -> None:
    logger().warning(msg)


def error(msg: str) -> None:
    logger().error(msg)
