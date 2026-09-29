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


def test_cube_not_implemented_yet(capsys):
    assert cli.main(["some_im.fits"]) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_import_does_not_load_heavy_modules():
    # a fresh interpreter: the test process may already have imported them
    code = ("import sys, explorer.cli; "
            "print(sorted(m for m in ('PySide6', 'numba', 'numpy', 'astropy') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"
