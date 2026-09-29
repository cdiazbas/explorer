"""Every test runs with its own cache directory and without a log file: tests never write to the user's
~/.cache/explorer (seen 2026-09-29: a budget warning from a test landed in the real log)."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    from explorer.obs import log

    log.setup(to_file=False)                            # console only, until a test asks for more
    yield
    log.setup(to_file=False)
