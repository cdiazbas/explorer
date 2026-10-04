"""What the window wears (ROADMAP E5.5, PLAN §3.6): a Look is data the views take, never methods patched over them.

- classic: the prototype's everyday window (its app/run.sh): red cursor and markers, the sliders in their colour,
  6-px rounded corners on the panels, the plots on black;
- modern: the prototype's proposal (its app/look.py, --modern), part by part (PARTS); EXPLORER_LOOK_OFF names parts
  to leave out, e.g. EXPLORER_LOOK_OFF=reticle,cards.
  - colour: a colour table per Stokes, on the image and lambda-t, with a colour key in the image's corner. Q U V
    start in grey, the same scale as I; the maps are a C away. Grey also keeps them at 1 B/px through the bridge;
  - cmap: C and Shift+C step through the maps for the Stokes shown, each Stokes keeping its own;
  - reticle: a short cross with a gap and a dark halo instead of two red lines across the image;
  - marks: the markers in the accent colour, quieter curves and grid, a zero line on Q U V;
  - cards: the plots on cards of the image's colour (black; white in the light theme);
The spectra's grid is quiet in both looks (alpha 0.07): at 0.2 its lines read as a mesh over the curves.
  - stokes: I Q U V as a segmented control, in a drop-down as narrow as the classic combo.
- glass: the modern look's parts but its cards, and its own (ui.glass): the image to the window's edges, the
  controls in a glass bar over it that hides itself, the panels floating beside it as smoked glass, the readout in
  the window's title, the markers in orange. The prototype's app/look_glass.py.
"""
import os
from dataclasses import dataclass

LOOKS = ("classic", "modern", "glass")
PARTS = ("colour", "cmap", "reticle", "marks", "cards", "stokes")
ENV_OFF = "EXPLORER_LOOK_OFF"


@dataclass(frozen=True)
class Look:
    name: str
    parts: frozenset

    def has(self, part: str) -> bool:
        return part in self.parts


def get_look(name: str = "classic", env=None) -> Look:
    if name not in LOOKS:
        raise ValueError(f"look {name!r}: one of {', '.join(LOOKS)}")
    if name == "classic":
        return Look("classic", frozenset())
    off = {p.strip() for p in (env if env is not None else os.environ).get(ENV_OFF, "").split(",") if p.strip()}
    parts = set(PARTS) - off
    if "colour" not in parts:                           # C steps through the colour tables: nothing without them
        parts.discard("cmap")
    if name == "glass":                                 # its panels float as smoked glass, not on modern's cards
        parts = (parts - {"cards"}) | {"glass"}
    return Look(name, frozenset(parts))
