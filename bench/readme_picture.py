"""The readme's picture of the window (.github/assets/explorer.png), offscreen: a cube in the modern look and the dark
theme, 1600x960, the cursor locked at a pixel, λ at a tuning. The window's title is "explorer", not the file's name,
and the picture holds no title bar.

    env -u DISPLAY QT_QPA_PLATFORM=offscreen PYTHONPATH=src python bench/readme_picture.py CUBE [--lock Y X] [--l L]

The picture of 2026-11-02: data/stokes_6173_im.fits on bellatrix (CRISP 6173, 186 scans), with the defaults: the
locked pixel at 45 % of y and 32 % of x (a sunspot's penumbra, so the four Stokes panels show signal), λ the middle
tuning (Δλ +0.026 Å), t the first scan. Set XDG_CONFIG_HOME and EXPLORER_LAYOUT to a scratch folder, or the window
rewrites the user's layout. The PNG is written at the highest compression (620 KB); a palette of its own saved 15 %
only, the granulation being texture.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), ".github", "assets", "explorer.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cube")
    ap.add_argument("--lock", nargs=2, type=int, metavar=("Y", "X"), help="the locked pixel (default: 45 %%, 32 %%)")
    ap.add_argument("--l", type=int, help="the λ tuning (default: the middle one)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)

    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from explorer.data.dataset import Dataset
    from explorer.look import get_look
    from explorer.ui import style, titlebar
    from explorer.ui.shell import Shell

    def spin(s, until=None):
        end = time.time() + s
        while time.time() < end and not (until is not None and until()):
            app.processEvents()
            time.sleep(0.004)

    style.apply_theme(app, "dark")
    with Dataset.open(a.cube) as ds:
        _nt, _ns, nl, ny, nx = ds.shape
        w = Shell(ds, title="explorer", look=get_look("modern"))
        titlebar.dock_titles(w)                         # the panels' titles as ui.app.start gives them (chrome)
        w.setGeometry(40, 40, 1600, 960)
        w.show()
        spin(60, lambda: w.first_image_s is not None)
        spin(1.0)
        w.reset_sizes()
        w.session.set_index("l", nl // 2 if a.l is None else a.l)
        y, x = a.lock if a.lock else (int(ny * 0.45), int(nx * 0.32))
        w.session.lock_at(y, x)
        spin(25, lambda: all(c.scheduler.img is not None for c in w.cubes))
        spin(8.0)                                       # the spectra and the lambda-t of the locked pixel
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        w.grab().save(a.out, "PNG", 0)                  # quality 0: the highest compression
        w.close()
        spin(0.5)
    print(f"{a.out}: {os.path.getsize(a.out) // 1024} KB, pixel ({y}, {x}), tuning {nl // 2 if a.l is None else a.l}")


if __name__ == "__main__":
    sys.exit(main())
