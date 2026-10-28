"""What the terminal says while a cube opens: its version and what it opens at once; each file that is away
(data.residency: its size with almost no blocks on disk, as StorNext leaves a file it moved to tape); and every few
seconds what it still waits for, until the first image (obs.waiting). A sparse file stands for the file on tape: the
same metadata, full size and no blocks. Offscreen; each test prints what it measured."""
import os
import re
import time

import pytest

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "golden", "data", "synth_small")


def sparse(path, size):
    """A file of size bytes with no blocks on disk (st_blocks 0), as a file moved to tape is left."""
    with open(path, "wb") as f:
        f.truncate(size)
    return str(path)


def test_a_file_with_its_size_and_no_blocks_is_away(tmp_path, monkeypatch):
    """residency: a sparse 100 MB file is 0 % on disk and away; a 2 MB file written whole is on disk (and under
    MIN_BYTES anyway, unless lowered); a missing file is neither. Before: no residency."""
    from explorer.data import residency

    far = sparse(tmp_path / "on_tape.fits", 100 << 20)
    whole = tmp_path / "whole.fits"
    whole.write_bytes(os.urandom(2 << 20))
    print("on disk:", residency.on_disk(far), residency.on_disk(whole), residency.on_disk(tmp_path / "missing"))
    assert residency.on_disk(far) == 0.0 and residency.on_disk(whole) >= 0.99
    assert residency.on_disk(tmp_path / "missing") is None
    monkeypatch.setattr(residency, "MIN_BYTES", 1 << 20)
    assert residency.away([far, str(whole), str(tmp_path / "missing"), None, far]) == [far]
    text = residency.away_text(far)
    print(text, "|", residency.on_disk_gb([far, str(whole)]))
    assert text.startswith("on_tape.fits: 0.1 GB, 0 % of it on disk") and "tape" in text
    assert residency.on_disk_gb([far]) == "on_tape.fits 0.0 of 0.1 GB on disk"


def test_the_waiting_lines_say_what_and_how_long_until_stopped(capsys):
    """obs.waiting: every `every` s an INFO line, what it waits for, the seconds and the extra; when nothing moves
    for `still` s (no CPU, nothing read, the extra's number the same), one WARN that says so and how to see the
    stacks; none after stop."""
    from explorer.obs.waiting import Waiting

    w = Waiting(time.perf_counter(), every=0.05, still=0.15, extra=lambda: ("0.0 of 91.9 GB on disk", 0.0))
    w.doing("opening cube.fits")
    time.sleep(0.4)
    w.stop()
    time.sleep(0.1)
    lines = capsys.readouterr().err.splitlines()
    time.sleep(0.2)
    after = capsys.readouterr().err
    print(len(lines), lines[:1], [x for x in lines if " WARN " in x])
    info = [x for x in lines if " INFO  still opening cube.fits: 0 s" in x]
    warn = [x for x in lines if " WARN  nothing has moved for " in x]
    assert len(info) >= 3 and all("0.0 of 91.9 GB on disk)" in x for x in info) and w.stopped and after == ""
    assert len(warn) == 1 and "while opening cube.fits" in warn[0] and f"kill -USR1 {os.getpid()}" in warn[0]


@pytest.fixture
def offscreen(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_start_says_its_version_and_what_it_opens_first(qapp, offscreen, capsys):
    """The first line, before anything is read: "HH:MM:SS INFO  explorer <version>: opening <file>"; the waiting
    lines stop at the first image. Before: the first line was the first image's."""
    from explorer import __version__
    from explorer.ui.app import start

    s = start(os.path.join(GOLDEN, "synth_small_im.fits"), saved_layout=False)
    assert s is not None
    try:
        assert spin(qapp, lambda: s.shell.first_image_s is not None)
        err = capsys.readouterr().err.splitlines()
        print(err[:3])
        ours = [e for e in err if re.match(r"\d\d:\d\d:\d\d (INFO |WARN |ERROR) ", e)]    # Qt's own notes aside
        assert re.fullmatch(rf"\d\d:\d\d:\d\d INFO  explorer {re.escape(__version__)}: opening synth_small_im.fits",
                            ours[0]), ours[0]
        assert s.shell.waiting is not None and s.shell.waiting.stopped
        assert not any("on disk" in line for line in err)                  # written whole: nothing away
    finally:
        s.shell.close()
        s.close()


def test_start_says_which_files_are_away_and_how_much_is_back(qapp, offscreen, capsys, monkeypatch):
    """Files away (here made so by residency.on_disk): a line for the cube and one for its per-pixel file found beside
    it, before they are read; the waiting lines then say how much of them is on disk."""
    from explorer.data import residency
    from explorer.ui import app

    monkeypatch.setattr(residency, "MIN_BYTES", 0)
    monkeypatch.setattr(residency, "on_disk", lambda p: 0.0)
    made = []

    def quick(*a, **k):                                 # a line every 0.05 s, kept to look at
        k["every"] = 0.05
        made.append(app.Waiting.__wrapped__(*a, **k))
        return made[-1]
    quick.__wrapped__ = app.Waiting
    monkeypatch.setattr(app, "Waiting", quick)
    s = app.start(os.path.join(GOLDEN, "synth_small_im.fits"), saved_layout=False)
    assert s is not None
    try:
        assert spin(qapp, lambda: s.shell.first_image_s is not None)
        err = capsys.readouterr().err.splitlines()
        away = [line for line in err if "of it on disk" in line]
        print(away)
        assert [line.split(" ", 1)[1].split(":")[0] for line in away] == ["WARN  synth_small_im.fits",
                                                                          "WARN  synth_small_sp.fits"]
        text, back = made[0].extra()
        assert "synth_small_sp.fits 0.0 of" in text and back == 0.0
    finally:
        s.shell.close()
        s.close()


def spin(qapp, until, timeout=10.0):
    end = time.perf_counter() + timeout
    while not until() and time.perf_counter() < end:
        qapp.processEvents()
        time.sleep(0.002)
    return until()
