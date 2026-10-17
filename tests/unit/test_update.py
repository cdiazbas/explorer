"""`explorer update`: a copy that is behind its remote's main is fast-forwarded and its version written; --check
changes nothing; a copy with changes, commits of its own, another branch, no git or no remote is left as it is,
and the reason said."""
import subprocess

import pytest

from explorer.update import update

ID = ["-c", "user.name=t", "-c", "user.email=t@example.org"]


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
    """origin (bare), dev (who pushes) and user (the copy updated), all on main, the user's copy one commit in."""
    origin, dev, user = tmp_path / "origin.git", tmp_path / "dev", tmp_path / "user"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(dev)], check=True, capture_output=True)
    git(dev, "switch", "-q", "-c", "main")
    commit(dev, "src/explorer/__init__.py", "", "[DEV] start")
    commit(dev, "uv.lock", "a\n", "[BUILD] pins")
    git(dev, "push", "-q", "origin", "main")
    subprocess.run(["git", "clone", "-q", "-b", "main", str(origin), str(user)], check=True, capture_output=True)
    return origin, dev, user


def run(user, check=False):
    said: list[str] = []
    return update(user, check=check, say=said.append), "\n".join(said)


def test_up_to_date(repos):
    _, _, user = repos
    rc, said = run(user)
    assert rc == 0 and "up to date" in said


def test_behind_check_changes_nothing_then_update_fast_forwards(repos):
    _, dev, user = repos
    before = git(user, "rev-parse", "HEAD")
    commit(dev, "a.txt", "1", "[DEV] first new")
    commit(dev, "b.txt", "2", "[DEV] second new")
    git(dev, "push", "-q", "origin", "main")
    rc, said = run(user, check=True)
    assert rc == 0 and "2 commit(s) behind origin/main" in said and "second new" in said and "first new" in said
    assert git(user, "rev-parse", "HEAD") == before and not (user / "src/explorer/_version.py").exists()
    rc, said = run(user)
    head = git(user, "rev-parse", "--short=9", "HEAD")
    assert rc == 0 and git(user, "rev-parse", "HEAD") == git(dev, "rev-parse", "HEAD")
    v = (user / "src/explorer/_version.py").read_text()
    assert f"0.0.1.dev4+g{head}" in v and f"updated to 0.0.1.dev4+g{head}" in said
    assert "rebuilds the environment" not in said                  # uv.lock did not change
    assert run(user)[1].endswith(")") and "up to date" in run(user)[1]


def test_new_pins_are_said(repos):
    _, dev, user = repos
    commit(dev, "uv.lock", "b\n", "[BUILD] new pins")
    git(dev, "push", "-q", "origin", "main")
    rc, said = run(user)
    assert rc == 0 and "the next start rebuilds the environment" in said


@pytest.mark.parametrize("case", ["changed", "branch", "ahead"])
def test_a_copy_with_its_own_work_is_left_as_it_is(repos, case):
    _, dev, user = repos
    commit(dev, "a.txt", "1", "[DEV] new")
    git(dev, "push", "-q", "origin", "main")
    if case == "changed":
        (user / "uv.lock").write_text("mine\n")
    elif case == "branch":
        git(user, "switch", "-q", "-c", "mine")
    else:
        commit(user, "mine.txt", "x", "[DEV] mine")
    before = git(user, "rev-parse", "HEAD")
    rc, said = run(user)
    assert rc == 1 and git(user, "rev-parse", "HEAD") == before
    assert {"changed": "tracked files changed", "branch": "on branch 'mine'", "ahead": "1 commit(s)"}[case] in said
    if case == "changed":
        assert (user / "uv.lock").read_text() == "mine\n"


def test_no_git_or_no_remote(repos, tmp_path):
    _, _, user = repos
    plain = tmp_path / "plain"
    plain.mkdir()
    rc, said = run(plain)
    assert rc == 1 and "not a git checkout" in said
    git(user, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    rc, said = run(user)
    assert rc == 1 and "cannot reach origin" in said
