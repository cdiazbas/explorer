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
    (f"written with {ASSISTANT}", "assistant mention"),
])
def test_finds_what_must_not_be_committed(line, kind):
    assert [f[1] for f in hygiene.scan_text("x", line)] == [kind]


def test_allows_the_shared_read_only_data_path():
    assert hygiene.scan_text("x", "FORBIDDEN = ['/mn/" + "path/to/the/shared/read-only/data']") == []


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
