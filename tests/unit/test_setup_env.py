"""scripts/setup_env.sh --link on an environment already up to date only makes the link (ROADMAP X.4): it installed
and checked everything again first. Run on a stand-in environment in a temporary folder whose python is a script,
with a stand-in uv first on the PATH: it answers --version, so the script takes it before any mamba or conda the
machine has, and fails at anything else. An install that should not happen stops at once and touches nothing (a
first version relied on finding no installer: GitHub's runners have conda, and pip went for the real interpreter the
stand-in linked to, stopped only by PEP 668).

The link's place and the PATH (ROADMAP X.3): asked of a new terminal of the user's shell, login and not, never of
this process; a startup file gets the marked block only when no usual folder is on that PATH, and a new terminal must
then find and run the link. Always in a temporary HOME: the real startup files are never read nor written."""
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


def _run(tmp_path, venv, *args, shell="/bin/bash"):
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    for name in ("uv", "conda"):                        # a conda too, as GitHub's runners have one
        f = tools / name
        f.write_text(FAKE_UV.replace("stand-in uv", f"stand-in {name}"))
        f.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin", "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "SHELL": shell}
    return subprocess.run(["/bin/bash", SCRIPT, "--venv", str(venv), *args], env=env, capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL)


def _stand_in(tmp_path, up_to_date=True, dev=False):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python"                         # runs, does nothing: never an interpreter of this machine
    py.write_text("#!/bin/sh\nexit 0\n")
    py.chmod(0o755)
    cmd = venv / "bin" / "explorer"                      # what run.sh hands over to
    cmd.write_text("#!/bin/sh\necho 'explorer 0.0 (stand-in)'\n")
    cmd.chmod(0o755)
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
    assert os.readlink(tmp_path / "home" / ".local" / "bin" / "explorer") == os.path.join(ROOT, "scripts", "run.sh")


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_link_on_an_environment_out_of_date_or_of_another_mode_installs(tmp_path):
    for case, venv_args in (("stale lock", dict(up_to_date=False)), ("dev asked, not built", dict(dev=False))):
        d = tmp_path / case.replace(" ", "_").replace(",", "")
        d.mkdir()
        p = _run(d, _stand_in(d, **venv_args), "--link", "--dev")
        assert "only the link" not in p.stdout, case
        assert "stand-in uv: python install" in p.stderr, case         # it went on to install (and stopped there)
        assert "stand-in conda" not in p.stderr, case


def _home(tmp_path, **files):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    for name, text in files.items():
        (home / name).write_text(text)
    return home


def _files(home):
    return {f.name: f.read_text() for f in home.iterdir() if f.is_file()}


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_a_usual_folder_already_on_a_new_terminals_path_takes_the_link_and_nothing_is_written(tmp_path):
    rc = 'case ":$PATH:" in *":$HOME/bin:"*) ;; *) PATH="$HOME/bin:$PATH" ;; esac\n'
    home = _home(tmp_path, **{".bashrc": rc, ".bash_profile": ". ~/.bashrc\n"})
    before = _files(home)
    p = _run(tmp_path, _stand_in(tmp_path), "--link")
    assert p.returncode == 0, p.stdout + p.stderr
    assert os.path.islink(home / "bin" / "explorer") and not (home / ".local" / "bin" / "explorer").exists()
    assert _files(home) == before and "explorer 0.0 (stand-in)" in p.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_without_one_bash_gets_the_block_in_bashrc_and_in_the_login_file_once(tmp_path):
    """No startup file at all (bellatrix's had none adding ~/.local/bin): a login shell reads ~/.profile, which does
    not read ~/.bashrc, so both get the block; a second run adds nothing."""
    home = _home(tmp_path)
    for _ in range(2):
        p = _run(tmp_path, _stand_in(tmp_path) if not (tmp_path / "venv").exists() else tmp_path / "venv", "--link")
        assert p.returncode == 0, p.stdout + p.stderr
        assert "a new terminal finds and runs it" in p.stdout
    files = _files(home)
    assert set(files) == {".bashrc", ".profile"}
    assert all(t.count(">>> explorer:") == 1 for t in files.values()), files
    assert all('export PATH="$HOME/.local/bin:$PATH"' in t and str(home) not in t for t in files.values()), files


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_a_login_file_that_reads_bashrc_is_left_alone(tmp_path):
    home = _home(tmp_path, **{".bash_profile": "[ -f ~/.bashrc ] && . ~/.bashrc\n"})
    p = _run(tmp_path, _stand_in(tmp_path), "--link")
    assert p.returncode == 0, p.stdout + p.stderr
    assert ">>> explorer:" in (home / ".bashrc").read_text()
    assert (home / ".bash_profile").read_text() == "[ -f ~/.bashrc ] && . ~/.bashrc\n"


@pytest.mark.skipif(sys.platform == "win32" or not os.path.exists("/bin/zsh"), reason="needs zsh")
def test_zsh_gets_the_block_in_zshrc(tmp_path):
    home = _home(tmp_path)
    p = _run(tmp_path, _stand_in(tmp_path), "--link", shell="/bin/zsh")
    assert p.returncode == 0, p.stdout + p.stderr
    assert set(_files(home)) == {".zshrc"} and ">>> explorer:" in (home / ".zshrc").read_text()


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_no_update_shell_writes_nothing_and_says_so(tmp_path):
    home = _home(tmp_path)
    p = _run(tmp_path, _stand_in(tmp_path), "--link", "--no-update-shell")
    assert p.returncode != 0 and "not on the PATH of a new terminal" in p.stderr
    assert _files(home) == {} and os.path.islink(home / ".local" / "bin" / "explorer")


@pytest.mark.skipif(sys.platform == "win32", reason="a bash script")
def test_another_explorer_first_on_the_path_is_reported(tmp_path):
    """A conda environment or an old install with its own `explorer` ahead of the link: the link would never run."""
    other = tmp_path / "other"
    other.mkdir()
    (other / "explorer").write_text("#!/bin/sh\necho other\n")
    (other / "explorer").chmod(0o755)
    _home(tmp_path, **{".bashrc": f'PATH="$PATH:$HOME/.local/bin"; PATH="{other}:$PATH"\n',
                       ".bash_profile": ". ~/.bashrc\n"})
    p = _run(tmp_path, _stand_in(tmp_path), "--link")
    assert p.returncode != 0 and f"finds another explorer first: {other}/explorer" in p.stderr, p.stderr
