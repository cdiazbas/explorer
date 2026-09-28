"""explorer: viewer for solar spectropolarimetric cubes [t, Stokes, lambda, y, x], successor of CRISPEX."""
try:
    from ._version import __version__
except ImportError:                     # running from a source tree that was never built or installed
    __version__ = "0.0.0+unknown"
