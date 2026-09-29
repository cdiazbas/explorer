#!/usr/bin/env python3
"""Keep the remote copy of explorer (bellatrix) in step with this one, as prototype/actualize.py did.

    python3 scripts/sync.py -n            # dry run: what push and pull would change
    python3 scripts/sync.py               # push (code) then pull (bench results)
    python3 scripts/sync.py push | pull

- This copy is the source of truth for code and notes; the remote produces measurements.
- push sends what git knows about: tracked files plus new files that .gitignore does not exclude. Before it,
  uv.lock is exported to requirements/*.txt (with hashes), because the remote has no uv and installs with pip.
- pull brings back bench/results/ only, and never overwrites a newer local file.
- Nothing is ever deleted on either side.
- push refuses while <remote>/.editing_on_server exists: someone is editing there, and a push would silently
  overwrite their work.
- It never opens a new ssh connection: it checks for an open ControlMaster first (`ssh -O check`, which connects
  to nothing) and stops if there is none. A new connection to bellatrix goes through login2, which sends a
  second-factor request to the user's phone; BatchMode does not prevent it, because the ProxyCommand's own ssh to
  login2 is not in batch mode, so without this check an expired master leaves a push waiting on that request.

Host and remote directory come from scripts/sync.local.json (never synced nor versioned: it holds a personal path):

    {"host": "bellatrix.uio.no", "remote_dir": "/path/to/projects/CRISPEX/explorer"}

Standard library only: runs with any python3 >= 3.8.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "scripts", "sync.local.json")
PULL = "bench/results/"
FORBIDDEN = ["/path/to/the/shared/read-only/data"]       # shared reduced data: read-only, never a target
EXPORTS = {                                           # uv.lock -> pip requirements, for machines without uv
    "requirements/lock.txt": ["--no-dev"],
    "requirements/lock-dev.txt": [],
}


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def export_requirements(dry):
    """Regenerate requirements/*.txt from uv.lock when the lock is newer (or they are missing)."""
    lock = os.path.join(ROOT, "uv.lock")
    stale = [p for p in EXPORTS if not os.path.exists(os.path.join(ROOT, p))
             or os.path.getmtime(os.path.join(ROOT, p)) < os.path.getmtime(lock)]
    if not stale:
        return
    if run(["uv", "--version"]).returncode:
        sys.exit(f"requirements/ is older than uv.lock and uv is not available here to export it: {stale}")
    for p in stale:
        print(f"  export {p} from uv.lock" + (" (dry run: skipped)" if dry else ""))
        if not dry:
            os.makedirs(os.path.join(ROOT, os.path.dirname(p)), exist_ok=True)
            r = run(["uv", "export", "--frozen", "--no-emit-project", "--quiet", "-o", p] + EXPORTS[p])
            if r.returncode:
                sys.exit(r.stderr)


def files_to_push():
    r = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    if r.returncode:
        sys.exit(f"git ls-files failed: {r.stderr.strip()}")
    return sorted({f for f in r.stdout.split("\0") if f and os.path.isfile(os.path.join(ROOT, f))})


def rsync(args, dry, stdin=None):
    cmd = ["rsync", "-a", "--itemize-changes"] + (["--dry-run"] if dry else []) + args
    print("$", " ".join(shlex.quote(c) for c in cmd), flush=True)
    r = run(cmd, input=stdin)
    out = [line for line in r.stdout.splitlines() if line and not line.startswith(".d")]  # hide unchanged dirs
    print("\n".join("  " + line for line in out) if out else "  (nothing to change)")
    if r.returncode:
        print("\n".join(line for line in r.stderr.splitlines() if "command not found" not in line), file=sys.stderr)
        sys.exit(r.returncode)


def remote(host, cmd):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", host, cmd], text=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", nargs="?", default="sync", choices=["sync", "push", "pull"])
    ap.add_argument("-n", "--dry-run", action="store_true", help="show what would change, touch nothing")
    a = ap.parse_args()
    if not os.path.exists(CONFIG):
        sys.exit(f"missing {os.path.relpath(CONFIG, ROOT)}; create it with:\n"
                 '  {"host": "bellatrix.uio.no", "remote_dir": "/path/to/projects/CRISPEX/explorer"}')
    cfg = json.load(open(CONFIG))
    host, rdir = cfg["host"], cfg["remote_dir"].rstrip("/")
    if any(rdir.startswith(f) for f in FORBIDDEN):
        sys.exit(f"refusing: {rdir} is read-only shared data")
    dest = f"{host}:{rdir}/"
    if subprocess.run(["ssh", "-O", "check", host], capture_output=True).returncode:
        sys.exit(f"no open ssh master to {host}: nothing done. Open one yourself (it asks for the second factor "
                 f"once, then lasts hours):\n  ssh -fN {host}\nand run this again.")

    if a.action in ("sync", "push"):
        r = remote(host, f"cat {shlex.quote(rdir)}/.editing_on_server 2>/dev/null")
        if r.stdout.strip():
            who = r.stdout.strip().replace("\n", "\n  ")
            print(f"refusing to push: {rdir}/.editing_on_server exists on {host}:\n  {who}\n"
                  "  bring those changes here first, then remove the file.", file=sys.stderr)
            if a.action == "push":
                sys.exit(1)
            a.action = "pull"                          # sync: still bring results back
    if a.action in ("sync", "push"):
        export_requirements(a.dry_run)
        files = files_to_push()
        print(f"--- push  local -> {dest}  ({len(files)} files)")
        if not a.dry_run:
            remote(host, f"mkdir -p {shlex.quote(rdir)}")
        rsync(["--files-from=-", "--from0", "./", dest], a.dry_run, stdin="\0".join(files))
    if a.action in ("sync", "pull"):
        print(f"--- pull  {dest}{PULL} -> {PULL}")
        exists = remote(host, f"test -d {shlex.quote(rdir + '/' + PULL)} && echo yes").stdout.strip() == "yes"
        if not exists:
            print("  (no results on the remote yet)")
        else:
            os.makedirs(os.path.join(ROOT, PULL), exist_ok=True)
            rsync(["--update", f"{dest}{PULL}", PULL], a.dry_run)       # never --delete


if __name__ == "__main__":
    main()
