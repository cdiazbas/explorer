#!/usr/bin/env python3
"""Repository hygiene: what must never be committed, checked on the tree, the history, or the staged changes.

    python3 scripts/hygiene.py              # tracked files and the whole history
    python3 scripts/hygiene.py --staged     # only what is staged (the pre-commit hook)
    python3 scripts/hygiene.py --message F  # a commit message (the commit-msg hook): the words, and the subject's form

Fails (exit 1) on:
- audit files in the repository (AUDIT*.md): they are local remediation checklists, never versioned;
- personal absolute paths in tracked text: a Mac home directory, a Linux home directory, any StorNext path;
- what the shared observations are, in tracked text or a commit message: their folders and their file names
  (instrument line, date and time). The data are private: the repository names them only through the generic
  links of data/; which file each link is lives in docs/data.local.md, which git ignores;
- mentions of AI assistants, or co-author trailers, in commit messages; mentions of AI assistants in any diff.

Binary files (a .npz reference, an image) are read too: their bytes, and each member of a zip (a .npz is one), as
Latin-1, UTF-16 and UTF-32 at every alignment. numpy writes its strings in UTF-32, which a plain grep never sees: a
golden reference carried a Mac home path in its metadata that way.

The words it looks for are composed from pieces, never written whole, so that this file and its tests do not
match themselves in the history. Standard library only.
"""
import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ASSISTANT = re.compile("|".join(["cla" + "ude", "anthro" + "pic"]), re.I)
_COAUTHOR = re.compile("co-" + "authored", re.I)
_AUDIT_NAME = re.compile(r"(^|/)" + "AUD" + r"IT[^/]*\.md$", re.I)
_PATHS = [
    ("Mac home path", re.compile("/" + "Users" + r"/[A-Za-z0-9._-]+")),
    ("Linux home path", re.compile("/" + "home" + r"/[A-Za-z0-9._-]+/")),
    ("StorNext path", re.compile("/mn/" + r"stornext/[^\s'\"`)\]]*")),
]
_OBSERVATIONS = [
    ("observation folder", re.compile("lap" + "alma|cubes" + "_nb", re.I)),
    ("observation file name", re.compile(r"(?<![A-Za-z])(nb|wb|B(los|hor|azi|inc|str)|Vlos|meinv|doppl|corew)[._]"
                                         r"\d{4}_\d{4}-\d{2}-\d{2}")),
]
TAGS = ("ADD", "DEV", "FIX", "PERF", "TEST", "BUILD", "DOC", "STYLE")      # docs/decisions/0005-commits.md
_SUBJECT = re.compile(r"^\[(" + "|".join(TAGS) + r")\] [a-z0-9`].{0,70}[^.]$")
CLOSING = ("ADD", "DEV", "FIX", "PERF")                                     # end with Behaviour: and Tests:
_BEHAVIOUR = re.compile(r"^Behaviour: (unchanged\b|changes \S)")


def git(*args) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, errors="replace")
    if r.returncode:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def scan_text(label: str, text: str):
    """Findings (label:line, kind, excerpt) for personal paths and assistant mentions in one text."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for kind, rx in _PATHS + _OBSERVATIONS:
            for m in rx.finditer(line):
                out.append((f"{label}:{n}", kind, m.group(0)[:60]))
        m = _ASSISTANT.search(line)
        if m:
            out.append((f"{label}:{n}", "assistant mention", line.strip()[:60]))
    return out


BINARY_MAX = 64 << 20                                   # bytes: a larger binary is not read


def binary_texts(blob: bytes):
    """(how, text): a binary's bytes as text in every encoding a string may hide in, each zip member apart."""
    parts = [("", blob)]
    if zipfile.is_zipfile(io.BytesIO(blob)):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            parts += [(f"{m.filename}: ", z.read(m)) for m in z.infolist() if m.file_size <= BINARY_MAX]
    for where, b in parts:
        yield f"{where}latin-1", b.decode("latin-1")
        for k in range(2):
            yield f"{where}utf-16 +{k}", b[k:].decode("utf-16-le", errors="ignore")
        for k in range(4):
            yield f"{where}utf-32 +{k}", b[k:].decode("utf-32-le", errors="ignore")


def scan_binary(label: str, blob: bytes):
    """scan_text over binary_texts, each finding once."""
    out, seen = [], set()
    for how, text in binary_texts(blob):
        for where, kind, excerpt in scan_text(f"{label} ({how})", text):
            if (kind, excerpt) not in seen:
                seen.add((kind, excerpt))
                out.append((where, kind, excerpt))
    return out


def check_files(names):
    out = []
    for name in names:
        if _AUDIT_NAME.search(name):
            out.append((name, "audit file in the repository", name))
            continue
        p = ROOT / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            if p.stat().st_size <= BINARY_MAX:
                out += scan_binary(name, p.read_bytes())
            continue
        except OSError:
            continue
        out += scan_text(name, text)
    return out


def check_history():
    out = []
    for n, line in enumerate(git("log", "--format=%h %B").splitlines(), 1):
        if _ASSISTANT.search(line) or _COAUTHOR.search(line):
            out.append((f"commit messages, line {n}", "assistant or co-author mention", line.strip()[:60]))
        for kind, rx in _OBSERVATIONS:
            if rx.search(line):
                out.append((f"commit messages, line {n}", kind, line.strip()[:60]))
    if _ASSISTANT.search(git("log", "-p", "--format=")):
        for c in git("log", "--format=%h").split():
            if _ASSISTANT.search(git("show", "--format=", c)):
                out.append((f"commit {c}", "assistant mention in its diff", ""))
    return out


def check_staged():
    names = [n for n in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if n]
    out = [(n, "audit file staged", n) for n in names if _AUDIT_NAME.search(n)]
    added = "\n".join(line[1:] for line in git("diff", "--cached", "--unified=0").splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    out += scan_text("staged changes", added)
    for n in names:                                     # binaries: the diff says only that they differ
        r = subprocess.run(["git", "show", f":{n}"], cwd=ROOT, capture_output=True)
        if r.returncode == 0 and len(r.stdout) <= BINARY_MAX:
            try:
                r.stdout.decode("utf-8")
            except UnicodeDecodeError:
                out += scan_binary(n, r.stdout)
    return out, names


def check_message(path):
    """The commit-msg hook: no assistant or co-author mention; a subject like "[TAG] one sentence", a blank line
    under it, and Behaviour: and Tests: closing [ADD] [DEV] [FIX] [PERF] (ADR 0005)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    out = []
    at = next((i for i, ln in enumerate(lines) if ln.strip()), 0)
    subject, rest = (lines[at], lines[at + 1:]) if lines else ("", [])
    m = _SUBJECT.match(subject)
    if not m and not subject.startswith(("Merge ", "Revert ")):
        out.append(("subject", "not '[TAG] one sentence' (ADR 0005)",
                    f"{subject[:60]!r}; tags: {', '.join(TAGS)}; lowercase start, <= 72 chars, no final period"))
    if rest and rest[0].strip():                     # git takes a body run into the subject as one long subject
        out.append(("message line 2", "no blank line after the subject (ADR 0005)", rest[0].strip()[:60]))
    if m and m.group(1) in CLOSING:
        if not any(_BEHAVIOUR.match(ln) for ln in rest):
            out.append(("body", f"no 'Behaviour:' line ([{m.group(1)}], ADR 0005 rule 3)",
                        "Behaviour: unchanged | changes <what>"))
        if not any(ln.startswith("Tests:") for ln in rest):
            out.append(("body", f"no 'Tests:' line ([{m.group(1)}], ADR 0005 rule 3)", "Tests: <what proves it>"))
    for n, ln in enumerate(lines, 1):
        if _ASSISTANT.search(ln) or _COAUTHOR.search(ln):
            out.append((f"message line {n}", "assistant or co-author mention", ln.strip()[:60]))
        for kind, rx in _OBSERVATIONS:
            if rx.search(ln):
                out.append((f"message line {n}", kind, ln.strip()[:60]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--staged", action="store_true", help="only the staged changes (pre-commit hook)")
    ap.add_argument("--message", metavar="FILE", help="check a commit message (commit-msg hook)")
    a = ap.parse_args()
    if a.message:
        findings, what = check_message(a.message), "the commit message"
    elif a.staged:
        findings, names = check_staged()
        what = f"{len(names)} staged files"
    else:
        tracked = [n for n in git("ls-files", "-z").split("\0") if n]
        findings = check_files(tracked) + check_history()
        what = f"{len(tracked)} tracked files and {len(git('log', '--format=%h').split())} commits"
    for where, kind, excerpt in findings:
        print(f"  FAIL  {kind:32s} {where}  {excerpt}")
    print(f"hygiene: {'FAILED' if findings else 'ok'} ({what}, {len(findings)} findings)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
