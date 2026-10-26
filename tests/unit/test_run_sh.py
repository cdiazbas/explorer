"""scripts/run.sh rebuilds only the environment of its own tree (ROADMAP X.6). It rebuilt whichever one it ran with
when the pins differed, $EXPLORER_VENV included: an old or experimental copy, started with the shared environment of
another tree, installed its own pins there, under everyone who runs that environment. The same through a copy whose
.venv-<OS>-<arch> is a link to another tree's environment, as the test copies in /tmp are made.

Run on a stand-in tree in a temporary folder: run.sh itself and the env.sh it sources, a uv.lock, and a setup_env.sh
that only writes down that it was called; the environments are stand-ins too, whose python and explorer are scripts.
No real environment is read or written."""
import os
import platform
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAT = f"{platform.system()}-{platform.machine()}"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a bash script")


def _tree(tmp_path, name="tree"):
    tree = tmp_path / name
    (tree / "scripts").mkdir(parents=True)
    for script in ("run.sh", "env.sh"):                        # run.sh sources env.sh
        shutil.copy(os.path.join(ROOT, "scripts", script), tree / "scripts" / script)
    setup = tree / "scripts" / "setup_env.sh"
    setup.write_text(f'#!/bin/sh\necho "$*" >> "{tmp_path}/setup_env.calls"\n')
    setup.chmod(0o755)
    (tree / "uv.lock").write_text(f"pins of {name}\n")
    return tree


def _venv(path, built_with="other pins\n"):
    (path / "bin").mkdir(parents=True)
    log = path.parent / f"{path.name}.python.calls"            # outside the environment: its files stay as they were
    for name, body in (("python", f'echo "$*" >> "{log}"'), ("explorer", 'echo "explorer ran: $*"')):
        f = path / "bin" / name
        f.write_text(f"#!/bin/sh\n{body}\nexit 0\n")
        f.chmod(0o755)
    lock = subprocess.run(["cksum"], input=built_with.encode(), capture_output=True).stdout
    (path / ".lock.cksum").write_bytes(lock)
    (path / ".dev").touch()
    return path


def _files(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


def _run(tree, venv=None):
    env = {"HOME": str(tree.parent / "home"), "PATH": "/usr/bin:/bin"}
    if venv is not None:
        env["EXPLORER_VENV"] = str(venv)
    return subprocess.run([str(tree / "scripts" / "run.sh"), "--version"], env=env, capture_output=True, text=True,
                          timeout=60, stdin=subprocess.DEVNULL)


def _calls(tmp_path):
    f = tmp_path / "setup_env.calls"
    return f.read_text().splitlines() if f.exists() else []


def test_another_trees_environment_is_left_as_it_is_and_runs(tmp_path):
    tree = _tree(tmp_path)
    shared = _venv(tmp_path / "shared" / f".venv-{PLAT}")
    before = _files(shared)
    p = _run(tree, venv=shared)
    assert p.returncode == 0 and "explorer ran: --version" in p.stdout, p.stdout + p.stderr
    assert _calls(tmp_path) == [], p.stderr                     # setup_env.sh never started on it
    assert _files(shared) == before
    assert "export.py" not in (tmp_path / "shared" / f".venv-{PLAT}.python.calls").read_text()   # nor explorer.app
    assert f"{shared} is not this tree's environment" in p.stderr and "unset EXPLORER_VENV, then" in p.stderr


def test_a_link_to_another_trees_environment_is_not_this_trees(tmp_path):
    """The layout of the test copies in /tmp: .venv-<OS>-<arch> a link to the shared tree's environment."""
    tree = _tree(tmp_path)
    shared = _venv(tmp_path / "shared" / f".venv-{PLAT}")
    os.symlink(shared, tree / f".venv-{PLAT}")
    before = _files(shared)
    p = _run(tree)
    assert p.returncode == 0 and "explorer ran: --version" in p.stdout, p.stdout + p.stderr
    assert _calls(tmp_path) == [] and _files(shared) == before, p.stderr
    assert f"remove the link {tree}/.venv-{PLAT}, then" in p.stderr         # setup_env.sh would build through it


@pytest.mark.parametrize("named", [False, True], ids=["default", "named by EXPLORER_VENV"])
def test_its_own_environment_is_rebuilt_when_the_pins_changed(tmp_path, named):
    tree = _tree(tmp_path)
    own = _venv(tree / f".venv-{PLAT}")
    p = _run(tree, venv=own if named else None)
    assert p.returncode == 0 and "explorer ran: --version" in p.stdout, p.stdout + p.stderr
    assert _calls(tmp_path) == [f"--venv {own} --dev"]


def test_its_own_environment_up_to_date_is_not_rebuilt(tmp_path):
    tree = _tree(tmp_path)
    _venv(tree / f".venv-{PLAT}", built_with=(tree / "uv.lock").read_text())
    p = _run(tree)
    assert p.returncode == 0 and _calls(tmp_path) == [] and p.stderr == "", p.stderr
