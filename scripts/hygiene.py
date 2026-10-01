#!/usr/bin/env python3
"""Repository hygiene: what must never be committed, checked on the tree, the history, or the staged changes.

    python3 scripts/hygiene.py              # tracked files and the whole history
    python3 scripts/hygiene.py --staged     # only what is staged (the pre-commit hook)
    python3 scripts/hygiene.py --message F  # a commit message (the commit-msg hook): the words, and the subject's form

Fails (exit 1) on:
- audit files in the repository (AUDIT*.md): they are local remediation checklists, never versioned;
- personal absolute paths in tracked text: a Mac home directory, a Linux home directory, or any StorNext
  path except the shared, read-only reduced data (the one allowed prefix below);
- mentions of AI assistants, or co-author trailers, in commit messages; mentions of AI assistants in any diff.

The words it looks for are composed from pieces, never written whole, so that this file and its tests do not
match themselves in the history. Standard library only.
"""
import argparse
import re
import subprocess
import sys
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
ALLOWED_PATHS = ("/path/to/the/shared/read-only/data",)   # shared reduced data; code refuses to write there
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
        for kind, rx in _PATHS:
            for m in rx.finditer(line):
                if not m.group(0).startswith(ALLOWED_PATHS):
                    out.append((f"{label}:{n}", kind, m.group(0)[:60]))
        m = _ASSISTANT.search(line)
        if m:
            out.append((f"{label}:{n}", "assistant mention", line.strip()[:60]))
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
        except (UnicodeDecodeError, OSError):
            continue                                    # binary: not ours to read
        out += scan_text(name, text)
    return out


def check_history():
    out = []
    for n, line in enumerate(git("log", "--format=%h %B").splitlines(), 1):
        if _ASSISTANT.search(line) or _COAUTHOR.search(line):
            out.append((f"commit messages, line {n}", "assistant or co-author mention", line.strip()[:60]))
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
