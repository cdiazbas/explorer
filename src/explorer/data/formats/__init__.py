"""On-disk formats: where the samples are and what they mean, without reading them.

    layout = open_layout(path)          # FITS or LP (icube/fcube), detected by content
    companions(path)                    # the per-pixel files next to an image cube
    opening(path, sp)                   # a per-pixel file given as a cube: its image cube, with it
    series_layout(paths)                # FITS images, one per file, as the t axis of one cube
    variables_layout(paths)             # a simulation snapshot's variables, a file each, as one cube
    idlsave.read(path)                  # the variables of an IDL save file (the one beside an LP cube: lp_sidecar)
"""
from . import idlsave
from .companions import Opening, companions, opening, per_pixel
from .detect import detect, open_layout
from .fits import fits_layout
from .layout import Layout
from .lp import LPHeader, lp_header, lp_pair_layouts, lp_sidecar, lp_single_layout, lp_values, scans_in_name
from .series import SeriesLayout, series_layout
from .variables import VariablesLayout, variables_layout

__all__ = ["Layout", "detect", "open_layout", "fits_layout", "LPHeader", "lp_header", "lp_pair_layouts",
           "lp_single_layout", "lp_sidecar", "lp_values", "scans_in_name", "companions", "Opening", "opening",
           "per_pixel", "idlsave", "SeriesLayout", "series_layout", "VariablesLayout", "variables_layout"]
