"""scripts/sync.py's list of what is on the remote and no longer pushed (ROADMAP E0.11): moved or deleted files are
listed; pulled results and what Python or an install makes there are not."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sync", os.path.join(HERE, "..", "..", "scripts", "sync.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def test_files_moved_or_deleted_here_are_listed():
    pushed = ["docs/journal.md", "src/explorer/cli.py"]
    remote = ["docs/journal.md", "docs/OVERVIEW.md", "src/explorer/cli.py", "src/explorer/old.py",
              "src/explorer/__pycache__/cli.cpython-312.pyc", "src/explorer/_version.py",
              "bench/results/linux/run.log", "src/explorer.egg-info/PKG-INFO"]
    assert sync.stale_files(remote, pushed) == ["docs/OVERVIEW.md", "src/explorer/old.py"]


def test_nothing_stale_nothing_listed():
    assert sync.stale_files(["a.py", "b/c.py"], ["a.py", "b/c.py"]) == []


def test_what_gitignore_keeps_out_is_not_listed():
    remote = ["tests/golden/real/stokes_6173.npz", "docs/old.md"]
    assert sync.stale_files(remote, [], ignored=["tests/golden/real/stokes_6173.npz"]) == ["docs/old.md"]


def test_also_carries_files_outside_git_to_the_same_place(tmp_path, monkeypatch, capsys):
    """sync.local.json's "also": notes kept beside the tree (outside git) go to the same place relative to the remote
    tree; one that is not here is skipped and said."""
    root = tmp_path / "proj" / "explorer"
    root.mkdir(parents=True)
    (tmp_path / "proj" / "NOTES.md").write_text("notes")
    monkeypatch.setattr(sync, "ROOT", str(root))
    calls = []
    monkeypatch.setattr(sync, "rsync", lambda args, dry, stdin=None: calls.append((args, dry)))
    sync.push_also(["../NOTES.md", "../missing.md"], "host", "/remote/proj/explorer", True)
    print(calls, capsys.readouterr().err)
    assert calls == [([str(tmp_path / "proj" / "NOTES.md"), "host:/remote/proj/NOTES.md"], True)]
