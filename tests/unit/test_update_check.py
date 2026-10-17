"""The update check (update_check): with a bare origin and two clones, a clone behind origin's main is told once per
new head, at most one ask of the remote a day; the same head, a clone with commits of its own, another branch, a tree
without git, the check turned off (or not asked, under pytest) say nothing; a git that never answers is killed with
what it started, silently, and waits for the next day. Nothing here reaches the network: origin is a folder."""
import os
import re
import shutil
import subprocess
import time

import pytest

from explorer import update_check as U

ID = ["-c", "user.name=t", "-c", "user.email=t@example.org"]
ON = {U.ENV: "1"}                                       # asked for, under pytest
T0 = 1_800_000_000.0


def git(d, *args):
    r = subprocess.run(["git", "-C", str(d), *ID, *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def commit(d, name, text, msg):
    (d / name).parent.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)
    git(d, "add", name)
    git(d, "commit", "-q", "-m", msg)


@pytest.fixture
def repos(tmp_path):
    """origin (bare), dev (who pushes) and user (the clone checked), all on main, the user's clone up to date."""
    origin, dev, user = tmp_path / "origin.git", tmp_path / "dev", tmp_path / "user"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(dev)], check=True, capture_output=True)
    git(dev, "switch", "-q", "-c", "main")
    commit(dev, "src/explorer/__init__.py", "", "[DEV] start")
    git(dev, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", "-b", "main", str(origin), str(user)], check=True, capture_output=True)
    return dev, user, tmp_path / "state.json"


def push(dev, name="a.txt"):
    commit(dev, name, name, f"[DEV] {name}")
    git(dev, "push", "-q", "origin", "main")
    return git(dev, "rev-parse", "HEAD")


def test_a_newer_head_is_announced_once_and_the_remote_asked_once_a_day(repos):
    dev, user, st = repos
    first = push(dev)
    f = U.check(user, ON, st, now=T0)
    assert f == U.Found(newer=True, announce=True, remote=first, local=git(user, "rev-parse", "HEAD"))
    assert U.check(user, ON, st, now=T0 + 60) == U.Found(True, False, first, f.local)     # said once
    second = push(dev, "b.txt")
    within = U.check(user, ON, st, now=T0 + U.EVERY_S - 1)
    assert within.remote == first and not within.announce      # the remote not asked again within the day
    next_day = U.check(user, ON, st, now=T0 + U.EVERY_S + 1)
    assert next_day == U.Found(True, True, second, f.local)   # a new head: said again, once
    saved = U.json.loads(st.read_text())[str(user.resolve())]
    assert saved == {"checked": T0 + U.EVERY_S + 1, "remote": second, "announced": second}


def test_up_to_date_says_nothing(repos):
    _dev, user, st = repos
    f = U.check(user, ON, st, now=T0)
    assert f is not None and not f.newer and not f.announce and f.remote == f.local


def test_after_the_update_the_head_seen_is_no_longer_newer(repos):
    dev, user, st = repos
    push(dev)
    assert U.check(user, ON, st, now=T0).newer
    git(user, "pull", "-q", "--ff-only")                        # `explorer update`'s fast-forward
    f = U.check(user, ON, st, now=T0 + 60)                      # within the day: the head seen, against HEAD now
    assert f is not None and not f.newer and not f.announce


def test_a_head_fetched_but_not_merged_is_newer(repos):
    dev, user, st = repos
    push(dev)
    git(user, "fetch", "-q")
    assert U.check(user, ON, st, now=T0).newer


@pytest.mark.parametrize("fetched", [True, False])
def test_a_clone_with_commits_of_its_own_is_not_told(repos, fetched):
    dev, user, st = repos
    commit(user, "mine.txt", "x", "[DEV] mine")
    if fetched:                                                 # origin's head known here: an ancestor of HEAD
        f = U.check(user, ON, st, now=T0)
    else:                                                       # origin moved on, never fetched: HEAD has its own
        push(dev)
        f = U.check(user, ON, st, now=T0)
    assert f is not None and not f.newer and not f.announce


def test_not_a_clone_on_main_is_not_asked(repos, tmp_path):
    dev, user, st = repos
    push(dev)
    synced = tmp_path / "synced"                                # a tree without git: copied or synced
    (synced / "src" / "explorer").mkdir(parents=True)
    assert U.check(synced, ON, st, now=T0) is None
    assert U.check(tmp_path / "site-packages", ON, st, now=T0) is None
    git(user, "switch", "-q", "-c", "mine")
    assert U.check(user, ON, st, now=T0) is None
    assert not st.exists()


def test_turned_off_or_under_tests_it_is_not_asked(repos):
    dev, user, st = repos
    push(dev)
    assert U.check(user, {U.ENV: "0"}, st, now=T0) is None
    assert U.check(user, {}, st, now=T0) is None               # pytest is imported here
    assert not st.exists()
    assert not U.wanted({U.ENV: "0"}) and U.wanted({U.ENV: "1", "PYTEST_CURRENT_TEST": "t"})
    assert not U.wanted({"PYTEST_CURRENT_TEST": "t"}) and not U.wanted({"QT_QPA_PLATFORM": "offscreen"})


def fake_git(tmp_path, monkeypatch, ls_remote: str):
    """A git on PATH that runs ls_remote (sh) for ls-remote, logging each call, and the real git otherwise."""
    real = shutil.which("git")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls"
    (bin_ / "git").write_text(f'#!/bin/sh\ncase "$*" in *ls-remote*) echo ls-remote >> "{calls}"; {ls_remote};; '
                              f'esac\nexec "{real}" "$@"\n')
    (bin_ / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    return calls


def test_a_git_that_never_answers_is_killed_with_what_it_started_and_said_nothing(repos, tmp_path, monkeypatch):
    dev, user, st = repos
    push(dev)
    pid = tmp_path / "pid"
    calls = fake_git(tmp_path, monkeypatch, f'sleep 60 & echo $! > "{pid}"; wait; exit 0')
    t = time.perf_counter()
    assert U.check(user, ON, st, now=T0, timeout=0.5) is None
    took = time.perf_counter() - t
    assert took < 5, took
    child = int(pid.read_text())                                # the sleep git started: killed with it
    end = time.perf_counter() + 3
    while time.perf_counter() < end:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"pid {child} still alive")
    assert U.check(user, ON, st, now=T0 + 60, timeout=0.5) is None     # the next ask is tomorrow's
    assert calls.read_text().split() == ["ls-remote"]


def test_git_is_asked_with_no_prompt_no_askpass_and_no_input(repos, tmp_path, monkeypatch):
    _dev, user, st = repos
    seen = tmp_path / "seen"
    fake_git(tmp_path, monkeypatch, f'echo "$GIT_TERMINAL_PROMPT|$GIT_ASKPASS|$GCM_INTERACTIVE|$(cat)" > "{seen}"; '
                                    'exit 128')
    assert U.check(user, ON, st, now=T0) is None                # a remote that refuses: nothing said
    assert seen.read_text().strip() == "0||never|"              # and stdin is empty: nothing can wait on it


def test_the_version_line(repos, tmp_path):
    _dev, user, _st = repos
    assert re.fullmatch(r"explorer 0\.0\.1\.dev1 · \d{4}-\d\d-\d\d", U.version_line(user)), U.version_line(user)
    from explorer import __version__

    assert U.version_line(tmp_path / "synced") == f"explorer {__version__.partition('+')[0]}"


def test_a_failed_ask_keeps_the_head_seen_before_and_says_it_no_second_time(repos, tmp_path, monkeypatch):
    dev, user, st = repos
    push(dev)
    assert U.check(user, ON, st, now=T0).announce
    fake_git(tmp_path, monkeypatch, "exit 128")                 # the next day, offline
    f = U.check(user, ON, st, now=T0 + U.EVERY_S + 1)
    assert f is not None and f.newer and not f.announce
