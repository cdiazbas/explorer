"""scripts/hygiene.py guards what must never be committed: if it broke silently, it would let exactly that through.
The forbidden words are composed from pieces here too, so this file never matches itself in the history."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("hygiene", Path(__file__).parents[2] / "scripts" / "hygiene.py")
hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hygiene)

ASSISTANT = "Cla" + "ude"
COAUTHOR = "Co-" + "Authored-By"


@pytest.mark.parametrize("line, kind", [
    ("data = '/" + "Users/someone/cube.fits'", "Mac home path"),
    ("cd /" + "home/someone/work/", "Linux home path"),
    ("see /mn/" + "stornext/d20/RoCS/someone/projects", "StorNext path"),
    ("data in /data/" + "lap" + "alma/somewhere", "observation folder"),
    ("open nb_" + "6173_2025-01-02T08:00:00_im.fits", "observation file name"),
    ("the B" + "los.6173_2024-01-02T09:00:00.fcube map", "observation file name"),
    (f"written with {ASSISTANT}", "assistant mention"),
])
def test_finds_what_must_not_be_committed(line, kind):
    assert [f[1] for f in hygiene.scan_text("x", line)] == [kind]


def test_generic_data_links_are_allowed():
    # what the repository may name: the generic links of data/, kinds and lines without date
    assert hygiene.scan_text("x", 'path = "../data/lp/stokes_6173_im.icube"  # Blos maps, nb_8542 clipped') == []


def test_an_observation_in_a_commit_message_is_refused(tmp_path):
    msg = tmp_path / "msg"
    msg.write_text("[DOC] notes\n\nas in nb_" + "6563_2024-01-02T09:19:23 next to it\n")
    assert [f[1] for f in hygiene.check_message(msg)] == ["observation file name"]


def test_audit_files_are_refused_by_name():
    assert hygiene.check_files(["docs/" + "AUD" + "IT_X.md"])[0][1] == "audit file in the repository"


@pytest.mark.parametrize("subject, ok", [
    ("[ADD] add the reader for icube files", True),
    ("[PERF] read frames with four preadv calls", True),
    ("[WIP] stuff", False),                               # not one of the tags
    ("[DOC] Capitalised subject", False),                 # lowercase start
    ("[DEV] ends with a period.", False),
    ("[DEV] " + "x" * 80, False),                         # too long
    ("add the reader", False),                            # no tag
])
def test_commit_subjects(tmp_path, subject, ok):
    p = tmp_path / "msg"
    p.write_text(subject + "\n\nBody.\n\nBehaviour: unchanged\nTests: none\n")
    assert (hygiene.check_message(p) == []) is ok


@pytest.mark.parametrize("body, found", [
    ("\nWhy.\n\nBehaviour: unchanged\nTests: test_x\n", []),
    ("Why, right under the subject.\n\nBehaviour: unchanged\nTests: test_x\n", ["no blank line after the subject"]),
    ("\nWhy.\n\nTests: test_x\n", ["no 'Behaviour:' line"]),
    ("\nWhy.\n\nBehaviour: unchanged\n", ["no 'Tests:' line"]),
    ("\nWhy.\n\nBehaviour: faster\nTests: test_x\n", ["no 'Behaviour:' line"]),   # unchanged | changes <what>
    ("\nBehaviour: changes the window\nTests: test_x\n", []),
])
def test_the_closing_lines_and_the_blank_line(tmp_path, body, found):
    """ADR 0005: [ADD] [DEV] [FIX] [PERF] end with Behaviour: and Tests:; the body starts after a blank line (git
    reads a body run into the subject as one long subject)."""
    p = tmp_path / "msg"
    p.write_text("[FIX] a fix\n" + body)
    assert [f[1].split(" (")[0] for f in hygiene.check_message(p)] == found


def test_other_tags_need_no_closing_lines(tmp_path):
    p = tmp_path / "msg"
    p.write_text("[DOC] a page\n\nWhy.\n")
    assert hygiene.check_message(p) == []


def test_co_author_trailer_is_refused(tmp_path):
    p = tmp_path / "msg"
    p.write_text(f"[DOC] fix a typo\n\n{COAUTHOR}: someone <a@b.c>\n")
    assert [f[1] for f in hygiene.check_message(p)] == ["assistant or co-author mention"]


@pytest.mark.parametrize("compressed", [False, True])
def test_a_path_in_a_numpy_file_is_found(tmp_path, compressed):
    """numpy writes its strings in UTF-32: a golden reference carried a Mac home path in its metadata, and a grep of
    the bytes never saw it. A clean file finds nothing."""
    import json

    import numpy as np

    save = np.savez_compressed if compressed else np.savez
    meta = json.dumps({"prototype": "/" + "Users/someone/prototype", "case": "x"})
    save(tmp_path / "ref.npz", meta=np.array(meta), a=np.arange(4.0))
    found = hygiene.scan_binary("ref.npz", (tmp_path / "ref.npz").read_bytes())
    assert [k for _w, k, _e in found] == ["Mac home path"], found
    save(tmp_path / "clean.npz", meta=np.array(json.dumps({"prototype": "../prototype"})), a=np.arange(4.0))
    assert hygiene.scan_binary("clean.npz", (tmp_path / "clean.npz").read_bytes()) == []


def test_a_path_in_a_numpy_file_anywhere_in_the_history_is_found(tmp_path, monkeypatch):
    """A version committed once and removed later is still in the history: it is read too."""
    import json
    import subprocess

    import numpy as np

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    meta = json.dumps({"prototype": "/" + "Users/someone/prototype"})
    np.savez_compressed(tmp_path / "ref.npz", meta=np.array(meta))
    git("add", "ref.npz")
    git("commit", "-q", "-m", "add")
    git("rm", "-q", "ref.npz")
    git("commit", "-q", "-m", "remove")
    monkeypatch.setattr(hygiene, "ROOT", tmp_path)
    found = hygiene.check_history_binaries()
    assert [k for _w, k, _e in found] == ["Mac home path"] and "ref.npz" in found[0][0], found


def test_a_branch_not_checked_out_and_the_stash_are_read_too(tmp_path, monkeypatch):
    """A leak on a branch other than HEAD, or in the stash, is still in the repository, and a push of that branch
    publishes it: the history scans read every local branch and every stash entry, not only HEAD's history."""
    import json
    import subprocess

    import numpy as np

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("clean\n")
    git("add", "a.txt")
    git("commit", "-q", "-m", "clean")
    git("checkout", "-q", "-b", "side")
    np.savez_compressed(tmp_path / "ref.npz", meta=np.array(json.dumps({"prototype": "/" + "Users/someone/p"})))
    (tmp_path / "b.txt").write_text(f"made with {ASSISTANT}\n")
    git("add", "ref.npz", "b.txt")
    git("commit", "-q", "-m", f"side\n\n{COAUTHOR}: someone <a@b.c>")
    git("checkout", "-q", "main")
    (tmp_path / "a.txt").write_text(f"stashed, by {ASSISTANT}\n")
    git("stash", "-q")
    monkeypatch.setattr(hygiene, "ROOT", tmp_path)
    kinds = sorted(k for _w, k, _e in hygiene.check_history())
    assert kinds == ["assistant mention in its diff"] * 2 + ["assistant or co-author mention"], kinds
    found = hygiene.check_history_binaries()
    assert [k for _w, k, _e in found] == ["Mac home path"] and "ref.npz" in found[0][0], found
