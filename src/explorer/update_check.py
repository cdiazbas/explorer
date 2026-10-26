"""Whether origin's main holds a newer explorer than this clone, asked in the background at start (ui.shell) so that
the window can say so: a note over the image, a line on the ? sheet. The update itself stays `explorer update`, by
hand (update.py).

    line, found = about()       # the version line of the ? sheet; Found, or None when not asked or on any failure

What it asks is read-only: `git ls-remote origin refs/heads/main`, and local git queries on what the clone already
has. Nothing is fetched and nothing in the clone is written; a remote that needs credentials gets them from the
helpers git is configured with, or fails: no prompt on any terminal (the process runs in a session of its own,
without one), no askpass program, no credential manager's window. After TIMEOUT_S it is killed with every process it
started (a keychain's dialog waiting for an answer, a network that does not answer), and nothing is said. As after
any fetch, a credential that worked is handed back to the helpers to keep (credential-store rewrites its file).

Asked at most once every EVERY_S; within that, the remote head seen last is compared with HEAD again (so after
`explorer update` it is no longer newer). Not asked when the code is not a git clone on main (a copy synced without
.git, a package installed with uv, pipx or pip: they are updated as they were made), after
`explorer update --no-notice` (until `--notice`), and under pytest or an offscreen run. EXPLORER_UPDATE_CHECK wins
over all of these: 0 never asks, 1 always does (what a test that asks for it sets).

A newer head is said in the window at once, and again every REMIND_DAYS while this copy stays behind: a note missed
in its seconds comes back.

State, per clone, in <cache>/update_check.json (_paths.cache_dir):
    {"<the clone's root>": {"checked": <unix time of the last ask>, "remote": "<head seen>",
                            "announced": "<head last said>", "shown": <unix time it was last said>,
                            "notice": false (only after --no-notice)}}
Standard library only.
"""
import atexit
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ._gitversion import git_version
from ._name import APP_NAME, ENV_PREFIX
from ._paths import cache_dir
from .update import BRANCH, REMOTE, ROOT

ENV = ENV_PREFIX + "UPDATE_CHECK"                       # 0: never asked; 1: asked under pytest or offscreen too
TIMEOUT_S = 3.0                                         # the remote's answer, at most; then killed, silently
EVERY_S = 24 * 3600                                     # the remote asked at most this often
REMIND_DAYS = 7                                         # a head already said, said again after this many days
STATE = "update_check.json"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")    # not the locale's
QUIET = {"GIT_TERMINAL_PROMPT": "0",                    # no username or password asked on a terminal
         "GIT_ASKPASS": "",                             # empty: no askpass program either (core.askPass included)
         "SSH_ASKPASS_REQUIRE": "never",                # ssh: no passphrase window
         "GCM_INTERACTIVE": "never"}                    # Git Credential Manager: no sign-in window

_running: set[subprocess.Popen] = set()                 # killed at exit: a check still waiting when the window closes


@dataclass(frozen=True)
class Found:
    newer: bool                 # origin's main has commits HEAD lacks, and HEAD none of its own
    announce: bool              # newer, and to be said now: a head not said before, or said REMIND_DAYS ago
    remote: str                 # origin's main, as ls-remote gave it now or within EVERY_S
    local: str                  # HEAD
    since: str = ""             # HEAD's commit date, YYYY-MM-DD ("" when git does not say)


def forced(env=None) -> bool | None:
    """EXPLORER_UPDATE_CHECK: False for 0, True for any other value, None when unset."""
    v = (os.environ if env is None else env).get(ENV, "").strip()
    return None if not v else v != "0"


def wanted(env=None, stored: bool = True) -> bool:
    """Whether the check runs here: as EXPLORER_UPDATE_CHECK says when set; unset, when notices are on for this clone
    (stored: notices()) and not under pytest nor offscreen."""
    env = os.environ if env is None else env
    f = forced(env)
    if f is not None:
        return f
    return stored and not ("PYTEST_CURRENT_TEST" in env or "pytest" in sys.modules
                           or env.get("QT_QPA_PLATFORM") == "offscreen")


def _kill_running() -> None:
    for p in list(_running):
        _kill(p)


atexit.register(_kill_running)


def _kill(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)                # git and what it started: remote-https, credential helpers
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _git(root, *args, timeout: float = TIMEOUT_S) -> tuple[int, str]:
    """(exit code, stdout) of git in root, with no input and no terminal; (-1, "") when it cannot run or overruns."""
    try:
        p = subprocess.Popen(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, env={**os.environ, **QUIET},
                             start_new_session=True)
    except OSError:                                     # no git on PATH
        return -1, ""
    _running.add(p)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        _kill(p)
        p.communicate()
        return -1, ""
    finally:
        _running.discard(p)


def is_clone(root) -> bool:
    """root is a git clone of explorer (its own .git, as `explorer update` asks), checked out on main."""
    root = Path(root)
    if not (root / ".git").exists() or not (root / "src" / APP_NAME).is_dir():
        return False
    rc, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return rc == 0 and branch.strip() == BRANCH


def state_path() -> Path:
    return cache_dir() / STATE


def _load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, state: dict) -> bool:
    """Written whole or not at all (another start may read it meanwhile); False when it cannot be written."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state, indent=1))
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _key(root) -> str:
    return str(Path(root).resolve())


def _entry(state: dict, root) -> dict:
    e = state.get(_key(root))
    return dict(e) if isinstance(e, dict) else {}


def notices(root=ROOT, path: Path | None = None) -> bool:
    """Whether notices are on for root as stored: on unless `explorer update --no-notice`; the env var aside."""
    return _entry(_load(state_path() if path is None else path), root).get("notice", True) is not False


def set_notices(root, on: bool, path: Path | None = None) -> Path | None:
    """Notices on or off for root, stored; the state file, None when it cannot be written."""
    path = state_path() if path is None else path
    state = _load(path)
    entry = _entry(state, root)
    if on:
        entry.pop("notice", None)
    else:
        entry["notice"] = False
    state[_key(root)] = entry
    return path if _save(path, state) else None


def _ls_remote(root, timeout: float) -> str | None:
    rc, out = _git(root, "ls-remote", REMOTE, f"refs/heads/{BRANCH}", timeout=timeout)
    sha = out.split()[0] if rc == 0 and out.split() else ""
    return sha if len(sha) >= 40 else None


def _newer(root, head: str, remote: str) -> bool:
    """remote has commits head lacks, and head none that remote lacks."""
    if remote == head:
        return False
    if _git(root, "cat-file", "-e", f"{remote}^{{commit}}")[0] == 0:   # already here (fetched, not merged)
        return _git(root, "merge-base", "--is-ancestor", head, remote)[0] == 0
    # A remote head this clone has never fetched: without a fetch git cannot say whether it descends from HEAD. It
    # is taken as newer when HEAD has no commits that origin/main lacked when last fetched: main on origin only
    # moves forward, so a remote head that differs is then ahead.
    rc, ahead = _git(root, "rev-list", "--count", f"refs/remotes/{REMOTE}/{BRANCH}..HEAD")
    return rc == 0 and ahead.strip() == "0"


def check(root=ROOT, env=None, path: Path | None = None, now: float | None = None,
          timeout: float = TIMEOUT_S) -> Found | None:
    """Whether origin's main is newer than root's HEAD (the module); None when not asked here, or on any failure.
    path: the state file (state_path()); now: time.time()."""
    if forced(env) is False or not is_clone(root):
        # a package installed with uv, pipx or pip has no clone and is not asked: `explorer update` says how to
        # update it (update.upgrade_advice). Once explorer is on PyPI (not while its name is provisional,
        # docs/decisions/0003), a check of PyPI's newest version against __version__ would go here
        return None
    path = state_path() if path is None else path
    state = _load(path)
    entry = _entry(state, root)
    if not wanted(env, stored=entry.get("notice", True) is not False):
        return None
    rc, head = _git(root, "rev-parse", "HEAD")
    head = head.strip()
    if rc or not head:
        return None
    now = time.time() if now is None else now
    remote, checked = entry.get("remote"), entry.get("checked")
    changed = not isinstance(checked, (int, float)) or not 0 <= now - checked < EVERY_S
    if changed:
        entry["checked"] = now                          # a failure waits for the next day too
        asked = _ls_remote(root, timeout)
        if asked is not None:                           # a failure: the head seen before, if any, compared again
            entry["remote"] = remote = asked
    newer = isinstance(remote, str) and _newer(root, head, remote)
    shown = entry.get("shown")
    announce = newer and (entry.get("announced") != remote or not isinstance(shown, (int, float))
                          or not 0 <= now - shown < REMIND_DAYS * 24 * 3600)
    if announce:
        entry["announced"], entry["shown"] = remote, now
    if changed or announce:
        state[_key(root)] = entry
        _save(path, state)
    if not isinstance(remote, str):                     # never seen: the ask failed
        return None
    rc, since = _git(root, "log", "-1", "--format=%cd", "--date=short")
    return Found(newer, announce, remote, head, since.strip() if rc == 0 else "")


def day_text(date: str) -> str:
    """'2026-10-02' -> '2 Oct 2026' (English months, whatever the locale); date as it came when it is not one."""
    try:
        y, m, d = (int(x) for x in date.split("-"))
        return f"{d} {MONTHS[m - 1]} {y}" if 1 <= m <= 12 else date
    except ValueError:
        return date


def version_line(root=ROOT) -> str:
    """'explorer 0.0.1.dev527 · 17 Oct 2026': the version without its local part (+g<hash>), and from a clone the
    date of its commit, written as the note writes it (day_text); from a copy without git, the version it was built
    or synced with (_version.py), no date."""
    if (Path(root) / ".git").exists():
        try:
            version, _sha = git_version(root)
        except OSError:                                 # no git on PATH
            version = ""
        rc, date = _git(root, "log", "-1", "--format=%cd", "--date=short")
        if version and rc == 0 and date.strip():
            return f"{APP_NAME} {version.partition('+')[0]} · {day_text(date.strip())}"
    from . import __version__
    return f"{APP_NAME} {__version__.partition('+')[0]}"


def about(root=ROOT, env=None) -> tuple[str, Found | None]:
    """(version_line, check): what the window's start asks in the background (ui.shell.Shell.start_update_check)."""
    return version_line(root), check(root, env)
