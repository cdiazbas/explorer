"""`explorer update`: a copy that is behind its remote's main is fast-forwarded and its version written; --check
changes nothing; a copy with changes, commits of its own, another branch, no git (synced, or a package installed
without a clone) or no remote is left as it is, and the reason said with what to do."""
import subprocess
import sys

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
    synced = tmp_path / "synced"                                 # a tree without git: copied or synced
    (synced / "src" / "explorer").mkdir(parents=True)
    (synced / "pyproject.toml").write_text("")
    rc, said = run(synced)
    assert rc == 1 and "a copy without git" in said and "whoever keeps it" in said
    package = tmp_path / "lib"                                   # pip install git+...: no source tree
    package.mkdir()
    rc, said = run(package)
    assert rc == 1 and "installed here as a package" in said and "pip install --upgrade git+https://" in said
    git(user, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    rc, said = run(user)
    assert rc == 1 and "cannot reach origin" in said


# what uv 0.11.15 and pipx 1.18.4 left in a tool's environment, measured (the paths here made up)
UV_RECEIPT = """[tool]
requirements = [{{ name = "explorer", {source} }}]
entrypoints = [
    {{ name = "explorer", install-path = "/srv/u/.local/bin/explorer", from = "explorer" }},
]
"""
PIPX_METADATA = """{{"main_package": {{"package": "explorer", "package_or_url": "{source}", "suffix": ""}},
 "pipx_metadata_version": "0.12", "venv_args": []}}"""


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """A package installed without a clone (no source tree beside it), in an environment at a sys.prefix of its own;
    its distribution named 'solar-explorer' (a rename, docs/decisions/0003)."""
    from importlib import metadata

    prefix, package = tmp_path / "venv", tmp_path / "venv" / "lib" / "python3.12"
    package.mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(metadata, "packages_distributions", lambda: {"explorer": ["solar-explorer"]})
    return prefix, package


@pytest.mark.parametrize("installer, source, says", [
    ("uv", 'git = "https://github.com/cdiazbas/explorer.git"', "as a uv tool: update it with `uv tool upgrade "
                                                               "solar-explorer`"),
    ("uv", 'directory = "/srv/u/explorer"', "`uv tool upgrade solar-explorer`"),
    ("uv", 'path = "/srv/u/dist/explorer-0.1-py3-none-any.whl"',
     "with uv from a wheel (/srv/u/dist/explorer-0.1-py3-none-any.whl), which `uv tool upgrade` cannot follow: "
     "install the newer wheel with `uv tool install --force <newer .whl>`"),
    ("pipx", "git+https://github.com/cdiazbas/explorer.git", "with pipx: update it with `pipx upgrade solar-explorer`"),
    ("pipx", "/srv/u/explorer", "`pipx upgrade solar-explorer`"),
    ("pipx", "/srv/u/dist/explorer-0.1-py3-none-any.whl", "`pipx install --force <newer .whl>`"),
    ("pip", "", "`pip install --upgrade git+https://github.com/cdiazbas/explorer.git`"),
])
def test_an_installed_package_is_told_its_installers_command(installed, installer, source, says):
    prefix, package = installed
    if installer == "uv":
        (prefix / "uv-receipt.toml").write_text(UV_RECEIPT.format(source=source))
    elif installer == "pipx":
        (prefix / "pipx_metadata.json").write_text(PIPX_METADATA.format(source=source))
    rc, said = run(package)
    assert rc == 1 and says in said, said
    assert "install from a clone (README, Install) to use `explorer update`" in said


def test_an_unreadable_record_still_names_the_installer(installed):
    prefix, package = installed
    (prefix / "uv-receipt.toml").write_text("not [toml")
    assert "`uv tool upgrade solar-explorer`" in run(package)[1]
    (prefix / "uv-receipt.toml").unlink()
    (prefix / "pipx_metadata.json").write_text("{")
    assert "`pipx upgrade solar-explorer`" in run(package)[1]


def test_a_copy_without_git_is_kept_by_whoever_keeps_it_whatever_the_environment(installed, tmp_path):
    prefix, _ = installed
    (prefix / "uv-receipt.toml").write_text(UV_RECEIPT.format(source='directory = "/x"'))
    synced = tmp_path / "synced"
    (synced / "src" / "explorer").mkdir(parents=True)
    (synced / "pyproject.toml").write_text("")
    rc, said = run(synced)
    assert rc == 1 and "a copy without git" in said and "uv tool" not in said


def test_an_update_ends_saying_a_running_explorer_needs_a_restart(repos):
    _, dev, user = repos
    commit(dev, "a.txt", "1", "[DEV] new")
    git(dev, "push", "-q", "origin", "main")
    rc, said = run(user, check=True)
    assert rc == 0 and "restart" not in said                     # nothing changed: nothing to restart
    rc, said = run(user)
    lines = said.splitlines()
    assert rc == 0 and lines[-1] == ("an explorer already running keeps the old code until it is restarted: "
                                     "restart explorer to use it")
    assert "restart" not in run(user)[1]                         # up to date: no restart either


def test_no_notice_and_notice_are_stored_said_and_reported_by_check(repos, monkeypatch):
    from explorer import update_check as uc
    from explorer.update import main

    _, dev, user = repos
    commit(dev, "a.txt", "1", "[DEV] new")
    git(dev, "push", "-q", "origin", "main")
    monkeypatch.delenv(uc.ENV, raising=False)
    assert "notices in the window: on (`explorer update --no-notice` turns them off)" in run(user, check=True)[1]
    said: list[str] = []
    assert main(["--no-notice"], root=user, say=said.append) == 0
    assert not uc.notices(user) and uc.state_path().exists()
    out = "\n".join(said)
    assert "notices off" in out and str(uc.state_path()) in out and "--notice` turns them back on" in out
    check = run(user, check=True)[1]
    assert "notices in the window: off (`explorer update --notice` turns them back on)" in check
    assert "overrides" not in check
    monkeypatch.setenv(uc.ENV, "1")                              # the env var wins, and --check says so
    assert "EXPLORER_UPDATE_CHECK=1 overrides this: on" in run(user, check=True)[1]
    said.clear()
    monkeypatch.setenv(uc.ENV, "0")
    assert main(["--notice"], root=user, say=said.append) == 0
    out = "\n".join(said)
    assert uc.notices(user) and "notices on" in out and str(uc.state_path()) in out
    assert "EXPLORER_UPDATE_CHECK=0 is set here, and overrides this" in said[-1]
    assert git(user, "rev-list", "--count", "HEAD") == "2"      # neither flag updates anything
    with pytest.raises(SystemExit):
        main(["--check", "--no-notice"], root=user)              # one thing at a time
