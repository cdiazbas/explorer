"""Observability for every layer: logging, timed spans with budgets, and Chrome/Perfetto traces.

Standard library only, and imports nothing else from explorer but its name and paths, so that any layer
(data included, which must not import Qt) can use it.

    from ..obs import get_logger, span, timed, counter
    log = get_logger("data.io")
    with span("image.read", idx=idx):
        ...
"""
from . import trace
from .log import get_logger, setup, setup_from_env
from .spans import budget, counter, enabled, set_enabled, span, summary, timed

__all__ = ["get_logger", "setup", "setup_from_env", "span", "timed", "counter", "budget", "summary", "enabled",
           "set_enabled", "trace"]
