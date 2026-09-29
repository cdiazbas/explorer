"""Every test runs with its own cache directory and without a log file, so that nothing a test logs or writes
(a budget warning, a doctor report) reaches the user's ~/.cache/explorer."""
import pytest


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
    from explorer.obs import log

    log.setup(to_file=False)                            # console only, until a test asks for more
    yield
    log.setup(to_file=False)
