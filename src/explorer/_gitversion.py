"""This tree's version from git, as the build's vcs versioning gives it, and the _version.py that says it: written by
scripts/sync.py (the remote copy has no git) and by `explorer update` (an editable install writes _version.py only
when it is reinstalled). Standard library only: sync.py imports it with the system's Python."""
import subprocess
import time
from pathlib import Path

VERSION_FILE = "src/explorer/_version.py"
VERSION_TEMPLATE = """# file generated from git by scripts/sync.py or `explorer update` (as the build's vcs-versioning)
# don't change, don't track in version control
__all__ = ["__version__", "__version_tuple__", "version", "version_tuple", "__commit_id__", "commit_id"]

__version__ = version = {version!r}
__version_tuple__ = version_tuple = {vtuple!r}

__commit_id__ = commit_id = {commit!r}
"""


def git(root, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def git_version(root) -> tuple[str, str]:
    """(version, short hash) as hatch-vcs gives it before the first tag (fallback 0.0.0): 0.0.1.dev<commits>+g<hash>,
    with .d<date> when tracked files have uncommitted changes. After a tag: git describe's."""
    sha = git(root, "rev-parse", "--short=9", "HEAD").stdout.strip()
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip())
    date = time.strftime(".d%Y%m%d") if dirty else ""
    d = git(root, "describe", "--tags", "--long", "--match", "v[0-9]*")
    if d.returncode == 0:                               # v1.2.3-<distance>-g<hash>
        tag, dist, _g = d.stdout.strip().rsplit("-", 2)
        base = tag.lstrip("v")
        if dist == "0" and not dirty:
            return base, sha
        parts = base.split(".")
        parts[-1] = str(int(parts[-1]) + 1) if parts[-1].isdigit() else parts[-1]
        return f"{'.'.join(parts)}.dev{dist}+g{sha}{date}", sha
    n = git(root, "rev-list", "--count", "HEAD").stdout.strip()
    return f"0.0.1.dev{n}+g{sha}{date}", sha


def version_file(version: str, sha: str) -> str:
    head, _, local = version.partition("+")
    vtuple = tuple(int(x) if x.isdigit() else x for x in head.split(".")) + ((local,) if local else ())
    return VERSION_TEMPLATE.format(version=version, vtuple=vtuple, commit=sha)


def stamp(root) -> str:
    """Write root's _version.py from git; its version."""
    version, sha = git_version(root)
    (Path(root) / VERSION_FILE).write_text(version_file(version, sha))
    return version
