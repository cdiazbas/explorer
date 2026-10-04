"""scripts/setup_env.sh --link on an environment already up to date only makes the link (ROADMAP X.4): it installed
and checked everything again first. Run on a stand-in environment in a temporary folder whose python is a script,
with a stand-in uv first on the PATH: it answers --version, so the script takes it before any mamba or conda the
machine has, and fails at anything else. An install that should not happen stops at once and touches nothing (a
first version relied on finding no installer: GitHub's runners have conda, and pip went for the real interpreter the
stand-in linked to, stopped only by PEP 668)."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "setup_env.sh")


FAKE_UV = """#!/bin/sh
[ "$1" = --version ] && { echo "uv 0.0.0 (stand-in)"; exit 0; }
echo "stand-in uv: $*" >&2
exit 3
"""


def _run(tmp_path, venv, *args):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("uv", "conda"):                        # a conda too, as GitHub's runners have one
        f = bin_dir / name
        f.write_text(FAKE_UV.replace("stand-in uv", f"stand-in {name}"))
        f.chmod(0o755)
    env = {"HOME": os.environ.get("HOME", str(tmp_path)), "PATH": f"{bin_dir}:/usr/bin:/bin",
           "XDG_BIN_HOME": str(bin_dir), "XDG_CACHE_HOME": str(tmp_path / "cache"), "SHELL": "/bin/bash"}
    return subprocess.run(["/bin/bash", SCRIPT, "--venv", str(venv), *args], env=env, capture_output=True, text=True,
                          timeout=60, stdin=subprocess.DEVNULL)


def _stand_in(tmp_path, up_to_date=True, dev=False):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python"                         # runs, does nothing: never an interpreter of this machine
    py.write_text("#!/bin/sh\nexit 0\n")
    py.chmod(0o755)
    lock = subprocess.run(["cksum"], stdin=open(os.path.join(ROOT, "uv.lock"), "rb"), capture_output=True).stdout
    (venv / ".lock.cksum").write_bytes(lock if up_to_date else b"0 0\n")
    if dev:
        (venv / ".dev").touch()
    return venv


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_link_on_an_environment_up_to_date_only_links(tmp_path):
    p = _run(tmp_path, _stand_in(tmp_path, dev=True), "--link", "--dev")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "only the link" in p.stdout and "== checking" not in p.stdout and "stand-in" not in p.stderr
    assert os.readlink(tmp_path / "bin" / "explorer") == os.path.join(ROOT, "scripts", "run.sh")


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_link_on_an_environment_out_of_date_or_of_another_mode_installs(tmp_path):
    for case, venv_args in (("stale lock", dict(up_to_date=False)), ("dev asked, not built", dict(dev=False))):
        d = tmp_path / case.replace(" ", "_").replace(",", "")
        d.mkdir()
        p = _run(d, _stand_in(d, **venv_args), "--link", "--dev")
        assert "only the link" not in p.stdout, case
        assert "stand-in uv: python install" in p.stderr, case         # it went on to install (and stopped there)
        assert "stand-in conda" not in p.stderr, case
