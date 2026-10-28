"""What explorer tells the person at the terminal (obs.say): "HH:MM:SS LEVEL message", the level padded to five,
later lines under the first; colour on the level only on a terminal, never with NO_COLOR; one line per message, not
again through the developers' console, whose warnings take the same form with their layer. Each test prints what it
measured."""
import io
import logging
import re

import pytest

LINE = re.compile(r"^\d\d:\d\d:\d\d (INFO |WARN |ERROR) ")


class Tty(io.StringIO):
    def isatty(self):
        return True


def test_a_line_is_time_level_and_message_with_later_lines_under_it():
    from explorer.obs import say

    one = say.line(logging.WARNING, "first\nsecond", when=0.0)
    print(repr(one))
    first, second = one.split("\n")
    assert LINE.match(first) and first.endswith("WARN  first") and second == say.INDENT + "second"
    assert say.line(logging.INFO, "x").split(" ", 1)[1] == "INFO  x"
    assert say.line(logging.ERROR, "x").split(" ", 1)[1] == "ERROR x"


def test_colour_only_on_a_terminal_and_never_with_no_color(monkeypatch):
    from explorer.obs import say

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert say.coloured(Tty()) and not say.coloured(io.StringIO())
    assert "\033[33mWARN \033[0m" in say.line(logging.WARNING, "x", colour=True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not say.coloured(Tty())
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not say.coloured(Tty())


def test_one_line_per_message_and_the_developers_warnings_alike(capsys):
    """After obs.log.setup (no log file, the console at WARNING): say's INFO and WARN once each on stderr
    (explorer.say keeps INFO and does not propagate to the console as well); a layer's warning as
    "WARN  data.io: ..."; a layer's INFO not on the console."""
    from explorer.obs import get_logger, say
    from explorer.obs.log import setup

    setup(to_file=False)
    say.info("opening a cube")                          # INFO still, whatever the console's level (WARNING)
    say.warn("a file on tape")
    get_logger("data.io").warning("a broken per-pixel file")
    get_logger("data.io").info("not for the console")
    err = capsys.readouterr().err.splitlines()
    print(err)
    assert len(err) == 3 and all(LINE.match(e) for e in err)
    assert err[0].endswith("INFO  opening a cube") and err[1].endswith("WARN  a file on tape")
    assert err[2].endswith("WARN  data.io: a broken per-pixel file")


@pytest.fixture(autouse=True)
def _logging_back():
    """explorer's loggers as they were (handlers, propagation, levels): obs.log.setup stops their propagation, and
    the tests after these read the root logger (caplog)."""
    names = ["explorer", "explorer.say", "explorer.data.io"]
    kept = {n: (list(logging.getLogger(n).handlers), logging.getLogger(n).propagate, logging.getLogger(n).level)
            for n in names}
    yield
    for n, (handlers, propagate, level) in kept.items():
        lg = logging.getLogger(n)
        for h in list(lg.handlers):
            if h not in handlers:
                lg.removeHandler(h)
                h.close()
        for h in handlers:
            if h not in lg.handlers:
                lg.addHandler(h)
        lg.propagate, lg.level = propagate, level
