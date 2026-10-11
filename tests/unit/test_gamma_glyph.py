"""Gamma as the window writes it, offscreen: 'γ = 0.79' with two significant figures (a third only where two would say 1
for a gamma that is not 1), and, where the text is painted, the γ in an italic serif from overlays.GAMMA_FAMILIES,
the first one installed, or the text's own font when none is; text without γ painted exactly as drawText paints it."""
import pytest

STEPS = [0.1, 0.126, 0.158, 0.2, 0.251, 0.316, 0.398, 0.501, 0.631, 0.794, 1.0, 1.26, 1.58, 2.0, 2.51, 3.16, 3.98,
         5.01, 6.31, 7.94, 10.0]


def test_the_text_says_gamma_equals_its_value_with_two_figures():
    from explorer.core.levels import gamma_step
    from explorer.ui.overlays import gamma_number, gamma_text

    assert gamma_text(10 ** -0.1) == "γ = 0.79" and gamma_text(1.0) == "γ = 1" and gamma_text(10.0) == "γ = 10"
    assert gamma_number(10 ** 0.1) == "1.3" and gamma_number(0.5) == "0.5" and gamma_number(0.1) == "0.1"
    assert gamma_number(1.03) == "1.03" and gamma_number(0.996) == "0.996"       # the card's slider near 1
    grid, g = [], 0.1
    while g < 10:                                       # every step of G: told apart by its text
        grid.append(gamma_number(g))
        g = gamma_step(g, 1)
    print("G's steps:", grid)
    assert len(grid) == len(set(grid)) == 20


class Recorder:
    """A QPainter's drawText seen from Python: (text, font) of each call, the painting done as usual."""

    def __init__(self, p):
        self.p, self.calls = p, []

    def __getattr__(self, name):
        return getattr(self.p, name)

    def drawText(self, *a):
        self.calls.append((a[-1], self.p.font()))
        return self.p.drawText(*a)


def _paint(text, align=None, families=None, monkeypatch=None):
    from PySide6 import QtCore, QtGui

    from explorer.ui import overlays

    if families is not None:
        monkeypatch.setattr(overlays, "GAMMA_FAMILIES", families)
    img = QtGui.QImage(200, 20, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QtGui.QPainter(img)
    f = QtGui.QFont()
    f.setFamilies(["Noto Sans", "DejaVu Sans", "Liberation Sans"])
    f.setPixelSize(11)
    p.setFont(f)
    p.setPen(QtGui.QColor("white"))
    rec = Recorder(p)
    try:
        overlays.draw_text(rec, QtCore.QRectF(0, 2, 200, 16), align or QtCore.Qt.AlignmentFlag.AlignHCenter, text)
    finally:
        p.end()                                         # a painter left open on a failure crashed the next GC
    return img, rec.calls, f


def test_the_painted_gamma_is_the_first_installed_italic_serif(qapp, monkeypatch):
    from PySide6 import QtGui

    from explorer.ui.overlays import GAMMA_FAMILIES, gamma_text

    _, calls, base = _paint(gamma_text(0.794))
    none = QtGui.QFontInfo(QtGui.QFont("No Such Family 0")).family()
    found = {f: QtGui.QFontInfo(QtGui.QFont(f)).family() for f in GAMMA_FAMILIES}   # fontconfig's names: "STIX"
    first = next((found[f] for f in GAMMA_FAMILIES if found[f] != none), None)
    got = [(t, QtGui.QFontInfo(f).family(), f.italic(), f.pixelSize()) for t, f in calls]
    print("found:", found, "runs:", got)
    assert "".join(t for t, *_ in got) == "γ = 0.79"
    (t, fam, italic, px), (t2, fam2, italic2, px2) = got
    assert t == "γ" and italic and px == 12 and not italic2 and px2 == 11
    assert fam2 == QtGui.QFontInfo(base).family()
    if first is None:
        pytest.skip("no family of GAMMA_FAMILIES installed here")
    assert fam == first != fam2


def test_without_those_families_the_gamma_is_the_text_s_own_font(qapp, monkeypatch):
    from PySide6 import QtGui

    _, calls, base = _paint("γ = 0.79", families=["No Such Family 0"], monkeypatch=monkeypatch)
    print("runs:", [(t, QtGui.QFontInfo(f).family(), f.italic()) for t, f in calls])
    assert QtGui.QFontInfo(calls[0][1]).family() == QtGui.QFontInfo(base).family() and calls[0][1].italic()


def test_text_without_gamma_is_drawtext_s_pixels(qapp):
    from PySide6 import QtCore, QtGui

    A = QtCore.Qt.AlignmentFlag
    for align in (A.AlignHCenter, A.AlignLeft | A.AlignVCenter, A.AlignRight | A.AlignVCenter):
        img, calls, f = _paint("drag ▲ · double click auto", align)
        ref = QtGui.QImage(200, 20, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        ref.fill(0)
        p = QtGui.QPainter(ref)
        p.setFont(f)
        p.setPen(QtGui.QColor("white"))
        p.drawText(QtCore.QRectF(0, 2, 200, 16), align, "drag ▲ · double click auto")
        p.end()
        assert len(calls) == 1 and img == ref


def test_the_key_paints_its_gamma_note_through_draw_text(qapp, monkeypatch):
    """The colour key's note after G and its name row with a gamma: both painted by draw_text."""
    from PySide6 import QtWidgets

    from explorer.ui import overlays

    seen = []
    real = overlays.draw_text
    monkeypatch.setattr(overlays, "draw_text", lambda p, r, a, t: (seen.append(t), real(p, r, a, t)))
    host = QtWidgets.QWidget()
    host.resize(400, 300)
    key = overlays.ColourKey(host)
    key.set("Stokes I", (0.0, 1.0), None, gamma=0.5)
    key.flash(overlays.gamma_text(10 ** -0.1))
    key.grab()
    print("painted:", seen)
    assert "γ = 0.79" in seen and any(t.endswith("γ = 0.5") for t in seen)
    host.deleteLater()
