"""The `explorer` command: version, help, subcommand dispatch, and that it stays light to import."""
import subprocess
import sys

import pytest

from explorer import __version__, cli


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"explorer {__version__}"


def test_no_arguments_prints_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "usage: explorer" in out and "doctor" in out


def test_a_cube_that_does_not_exist(capsys):
    assert cli.main(["some_im.fits"]) == 2
    assert "no such file" in capsys.readouterr().err


def test_import_does_not_load_heavy_modules():
    # a fresh interpreter: the test process may already have imported them
    code = ("import sys, explorer.cli; "
            "print(sorted(m for m in ('PySide6', 'numba', 'numpy', 'astropy') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


def test_demo_as_an_option_too(monkeypatch):
    """explorer --demo is explorer demo (the synthetic cube unless one is given), as one would guess it."""
    import importlib

    from explorer import cli

    seen = []
    fake = type("M", (), {"main": staticmethod(lambda argv: seen.append(argv) or 0)})
    real = importlib.import_module
    monkeypatch.setattr(importlib, "import_module", lambda name, pkg=None: fake if name == ".demo" else real(name, pkg))
    assert cli.main(["--demo"]) == 0 and cli.main(["--demo", "x_im.fits"]) == 0
    assert seen == [[], ["x_im.fits"]]


def test_a_foreign_library_path_is_left_behind_on_linux(tmp_path):
    """Another environment's LD_LIBRARY_PATH (conda's, from .bashrc) breaks PySide6 (Qt_6_PRIVATE_API): the
    command starts again without it, or with .qtlibs/only alone (prototype's test.py:19-28). Once only, and never
    on a Mac."""
    from explorer import cli

    (tmp_path / ".qtlibs" / "only").mkdir(parents=True)
    env = {"LD_LIBRARY_PATH": "/opt/conda/envs/kdb/lib", "HOME": "/h"}
    new = cli.clean_library_path(env, "linux", str(tmp_path))
    assert new is not None and new["LD_LIBRARY_PATH"] == str(tmp_path / ".qtlibs" / "only") and new["HOME"] == "/h"
    assert cli.clean_library_path(new, "linux", str(tmp_path)) is None                 # started again: once only
    assert cli.clean_library_path({"LD_LIBRARY_PATH": str(tmp_path / ".qtlibs" / "only")}, "linux",
                                  str(tmp_path)) is None                              # as run.sh sets it
    assert "LD_LIBRARY_PATH" not in cli.clean_library_path(env, "linux", str(tmp_path / "no_qtlibs"))
    assert cli.clean_library_path({}, "linux", str(tmp_path / "no_qtlibs")) is None  # nothing to clean
    assert cli.clean_library_path(env, "darwin", str(tmp_path)) is None
