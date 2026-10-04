"""The application icon's files for the operating systems, all drawn from src/explorer/ui/assets/explorer.svg: one
source, nothing here is edited by hand, and nothing written is tracked by git.

    python tools/icons/export.py [OUT]        OUT: build/icons by default (git ignores build/)
    python tools/icons/export.py --app ENV/explorer.app --exe ENV/bin/python      (scripts/setup_env.sh, macOS)

Writes into OUT:
- png/explorer-<n>.png, n = 16 24 32 48 64 128 256 512 1024;
- explorer.ico: Windows, PNG entries of 16 24 32 48 256 (the form Windows Vista and later read);
- explorer.icns: macOS, by iconutil from an .iconset (on a Mac only; elsewhere it says so and goes on);
- hicolor/<n>x<n>/apps/explorer.png and hicolor/scalable/apps/explorer.svg: the freedesktop icon theme's layout,
  for a desktop entry (roadmap X.1). Nothing is installed into the home directory.
With --app, only a minimal macOS app bundle around the environment's Python (app_bundle): scripts/run.sh starts
explorer through it, so that the Dock shows explorer's icon from launch.
Runs with explorer's venv (PySide6's QtSvg), offscreen: no display is needed.
"""
import argparse
import os
import plistlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "src" / "explorer" / "ui" / "assets" / "explorer.svg"
NAME = "explorer"
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 256)
HICOLOR_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
# iconutil's names: <points>x<points>[@2x], from 16 to 512 points
ICONSET = {f"icon_{p}x{p}{'@2x' if k == 2 else ''}.png": p * k for p in (16, 32, 128, 256, 512) for k in (1, 2)}
LAUNCHER_ENV = "__PYVENV_LAUNCHER__"                   # the environment's python, for one started from a bundle
_app = None                                             # the offscreen application, kept while the script runs


def renderer(svg: Path):
    """A QSvgRenderer of svg, with the offscreen application Qt needs to draw (the running one if there is one)."""
    from PySide6 import QtGui, QtSvg

    global _app
    if QtGui.QGuiApplication.instance() is None:
        _app = QtGui.QGuiApplication(["export", "-platform", "offscreen"])
    r = QtSvg.QSvgRenderer(str(svg))
    if not r.isValid():
        sys.exit(f"cannot read {svg} as SVG")
    return r


def png(r, n: int) -> bytes:
    """The SVG drawn on n x n transparent pixels, as PNG bytes."""
    from PySide6 import QtCore, QtGui

    im = QtGui.QImage(n, n, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    im.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(im)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    r.render(p, QtCore.QRectF(0, 0, n, n))
    p.end()
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not im.save(buf, "PNG"):
        sys.exit(f"cannot encode the {n} px image as PNG")
    return bytes(buf.data().data())


def ico(pngs: dict[int, bytes]) -> bytes:
    """An ICO of PNG entries: the directory (reserved 0, type 1 = icon, count), one 16-byte entry per image (width
    and height, 0 meaning 256; no palette; 1 plane; 32 bits; size and offset of its data), then the PNG data."""
    sizes = sorted(pngs)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(head) + 16 * len(sizes)
    entries, data = b"", b""
    for n in sizes:
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(pngs[n]), offset + len(data))
        data += pngs[n]
    return head + entries + data


def icns(pngs: dict[int, bytes], out: Path) -> Path | None:
    """explorer.icns by iconutil from an .iconset (removed afterwards); None where there is no iconutil."""
    tool = shutil.which("iconutil")
    if sys.platform != "darwin" or tool is None:
        print("explorer.icns: skipped (iconutil is macOS's)")
        return None
    iconset = out / f"{NAME}.iconset"
    iconset.mkdir(exist_ok=True)
    for name, n in ICONSET.items():
        (iconset / name).write_bytes(pngs[n])
    target = out / f"{NAME}.icns"
    subprocess.run([tool, "-c", "icns", "-o", str(target), str(iconset)], check=True)
    shutil.rmtree(iconset)
    return target


def export(out: Path, svg: Path = SVG) -> list[Path]:
    """Every file above into out; returns the paths written."""
    r = renderer(svg)
    pngs = {n: png(r, n) for n in sorted(set(PNG_SIZES) | set(ICO_SIZES) | set(HICOLOR_SIZES))}
    written = []

    def put(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)

    for n in PNG_SIZES:
        put(out / "png" / f"{NAME}-{n}.png", pngs[n])
    put(out / f"{NAME}.ico", ico({n: pngs[n] for n in ICO_SIZES}))
    made = icns(pngs, out)
    if made is not None:
        written.append(made)
    for n in HICOLOR_SIZES:
        put(out / "hicolor" / f"{n}x{n}" / "apps" / f"{NAME}.png", pngs[n])
    put(out / "hicolor" / "scalable" / "apps" / f"{NAME}.svg", svg.read_bytes())
    return written


def app_bundle(app: Path, exe: Path, svg: Path = SVG) -> Path:
    """app: a minimal app bundle whose executable, Contents/MacOS/explorer, is a link to exe (an environment's
    python), its Info.plist naming Resources/explorer.icns. A process started through the link is the bundle's for
    LaunchServices, which gives the Dock the bundle's icon from launch; a bare executable's is a blank document until
    the application sets its own. LAUNCHER_ENV=exe tells that Python its environment (Python unsets it at start).
    Made whole beside app, then put in its place; on a Mac its Python must find exe's environment, else it is
    removed."""
    tmp = app.with_name(app.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "Contents" / "MacOS").mkdir(parents=True)
    (tmp / "Contents" / "Resources").mkdir()
    r = renderer(svg)
    icns({n: png(r, n) for n in set(ICONSET.values())}, tmp / "Contents" / "Resources")
    info = {"CFBundleExecutable": NAME, "CFBundleIconFile": NAME, "CFBundleIdentifier": f"local.{NAME}.viewer",
            "CFBundleName": NAME, "CFBundleDisplayName": NAME, "CFBundlePackageType": "APPL",
            "CFBundleInfoDictionaryVersion": "6.0", "NSHighResolutionCapable": True}
    (tmp / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    (tmp / "Contents" / "MacOS" / NAME).symlink_to(exe)
    shutil.rmtree(app, ignore_errors=True)
    tmp.rename(app)
    if sys.platform == "darwin":
        def prefix(cmd, env):
            p = subprocess.run([cmd, "-c", "import sys; print(sys.prefix)"], env=env, capture_output=True, text=True)
            return p.stdout.strip() if p.returncode == 0 else f"failed: {p.stderr.strip()[-300:]}"

        want = prefix(str(exe), dict(os.environ))
        got = prefix(str(app / "Contents" / "MacOS" / NAME), dict(os.environ, **{LAUNCHER_ENV: str(exe)}))
        if got != want:
            shutil.rmtree(app)
            sys.exit(f"{app}: removed, its Python does not find the environment of {exe} ({got}, not {want})")
    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", nargs="?", default=str(ROOT / "build" / "icons"))
    ap.add_argument("--svg", default=str(SVG), help="the source (default: the application's)")
    ap.add_argument("--app", help="only the app bundle, at this path (NAME.app)")
    ap.add_argument("--exe", default=sys.executable, help="the bundle's executable: the environment's python")
    a = ap.parse_args(argv)
    if a.app:
        print(app_bundle(Path(a.app), Path(a.exe), Path(a.svg)))
        return 0
    out = Path(a.out)
    written = export(out, Path(a.svg))
    print(f"{len(written)} files in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
