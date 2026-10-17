"""`explorer update`: bring this copy of explorer to the latest main of its git remote, by hand when its owner says
there is something new; never at start (a change would reach everyone at once, in the middle of an analysis, and
the remote is private: every start would need the network and credentials).

    explorer update            # how far behind, then a fast-forward to origin/main, and the version after it
    explorer update --check    # how far behind, and the commits it would bring; nothing changed

Refuses, saying why, when this copy is not a git checkout (a shared copy kept in step by its owner), is on another
branch, has changes to tracked files, or has commits of its own: nothing is merged, stashed nor thrown away. The
environment is not touched here: scripts/run.sh (the `explorer` command) rebuilds it at the next start when the
pinned versions (uv.lock) changed.
"""
import argparse
import sys
from pathlib import Path

from ._gitversion import git, stamp
from ._name import APP_NAME

ROOT = Path(__file__).resolve().parents[2]              # src/explorer/update.py -> the tree
BRANCH, REMOTE = "main", "origin"
SHOWN = 15                                              # commits listed at most


def _say(text: str) -> None:
    print(f"[{APP_NAME} update] {text}")


def update(root=ROOT, check: bool = False, say=_say) -> int:
    """0: up to date or brought up to date (or, with check, only said); 1: refused or failed, and why said."""
    root = Path(root)
    if git(root, "rev-parse", "--is-inside-work-tree").returncode or not (root / ".git").exists():
        say(f"{root} is not a git checkout: it is kept up to date by whoever keeps it, not from here")
        return 1
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        say(f"on branch {branch!r}: updates follow {BRANCH}; `git -C {root} switch {BRANCH}` first")
        return 1
    changed = git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if changed:
        say("tracked files changed here; nothing done, so that nothing is lost:\n" + changed)
        return 1
    f = git(root, "fetch", "--quiet", REMOTE, BRANCH)
    if f.returncode:
        say(f"cannot reach {REMOTE} (network, or access to the repository): {f.stderr.strip()}")
        return 1
    up = f"{REMOTE}/{BRANCH}"
    behind = int(git(root, "rev-list", "--count", f"HEAD..{up}").stdout.strip() or 0)
    ahead = int(git(root, "rev-list", "--count", f"{up}..HEAD").stdout.strip() or 0)
    head = git(root, "log", "-1", "--format=%h, %cd", "--date=short").stdout.strip()
    if ahead:
        say(f"this copy has {ahead} commit(s) {up} does not: nothing done (push or drop them first)")
        return 1
    if not behind:
        say(f"up to date ({head})")
        return 0
    log = git(root, "log", "--format=  %h %cd %s", "--date=short", f"-{SHOWN}", f"HEAD..{up}").stdout.rstrip()
    more = f"\n  ... and {behind - SHOWN} more" if behind > SHOWN else ""
    say(f"{behind} commit(s) behind {up} (this copy: {head}):\n{log}{more}")
    if check:
        return 0
    lock = bool(git(root, "diff", "--name-only", f"HEAD..{up}", "--", "uv.lock").stdout.strip())
    m = git(root, "merge", "--ff-only", "--quiet", up)
    if m.returncode:
        say(f"the fast-forward failed, nothing changed: {m.stderr.strip()}")
        return 1
    version = stamp(root)
    now = git(root, "log", "-1", "--format=%h, %cd", "--date=short").stdout.strip()
    say(f"updated to {version} ({now})" + ("; the pinned versions changed: the next start rebuilds the environment"
                                           " (scripts/run.sh)" if lock else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"{APP_NAME} update", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only say how far behind, and what it would bring")
    a = ap.parse_args(argv)
    return update(check=a.check)


if __name__ == "__main__":
    sys.exit(main())
