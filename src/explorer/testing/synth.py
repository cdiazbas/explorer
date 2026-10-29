"""Small synthetic cubes shaped like SST reduced data (SSTRED), deterministic, for tests, demos and the comparison
against the prototype:

    paths = write_dataset(directory, "synth_stokes")   # {"im": ..._im.fits, "sp": ..._sp.fits, "icube": ..._sp.icube}

- _im.fits: numpy (t, s, lambda, y, x), big-endian float32, NaN padding around a rotated field of view, so that
  every code path that must handle padding (levels, colour tables, samples, reads skipped) is exercised.
- The header follows the Fe I 6173 cube (SOLARNET 1.0) as the prototype reads it (app/physics.py): CTYPE
  HPLN-TAB, HPLT-TAB, WAVE-TAB, STOKES, UTC--TAB; PSi_0/PSi_1/PSi_2 pointing to a WCS-TAB binary table whose
  column "HPLN+HPLT+WAVE+TIME" has shape (nt, nl, 2, 2, 4), with HPLN-INDEX and HPLT-INDEX; WAVEBAND, DATEREF,
  BUNIT; the continuum tuning in the PRPARA of the STOKES-CROSSTALK-CORRECTION step. The pointing drifts a
  little with t, so per-time pointing can be tested. No WCSDVARR (the prototype does not apply it either).
- _sp.fits: the same values transposed to numpy (y, x, s, t, lambda), as SSTRED writes it.
- _sp.icube: LP (La Palma) cube, 512-byte ASCII header as in the real nb_6563 _sp.icube ("stokes=[I], ns=1 :
  datatype=2 (integer), dims=3, nx=nl, ny=nt, nt=npix*ns, endian=l"), little-endian int16, pixel-major with Stokes
  fastest (prototype app/sources.py SpLP). Values = round(1e11 * value), the scaling of the real nb_6563
  _sp.icube (synthetic cube v2). SSTRED's red__fitscube_integer.pro scales differently (global
  [DATAMIN, DATAMAX] -> +-32000 with BSCALE/BZERO), so readers must not assume a scale: the prototype fits scale
  and zero against the FITS cube and ignores zero counts (app/sources.py SpLP.calibrate); NaN is written as 0.
Physics is only plausible: granulation, a spot and a pore, an absorption line whose Doppler shift drifts in t,
V antisymmetric in lambda, Q and U from the spot's azimuth, and a continuum tuning far in the red wing.
"""
import json
import os

import numpy as np

SYNTH_VERSION = 2                       # bump when the content changes: cached demo cubes are then rewritten
DEFAULT_SHAPE = (8, 4, 10, 256, 256)    # (t, s, lambda, y, x): 84 MB per float32 file
LINE_NM = 617.3341                      # Fe I 6173, laboratory, air (the prototype's LINES table)
ICUBE_SCALE = 1e11                      # as the real nb_6563 _sp.icube (see the module docstring)
DATE = "2025-07-11"
T0_S, CADENCE_S, TUNING_S = 29819.0, 20.0, 0.25      # first exposure after DATEREF, per scan, per tuning
PIXEL_ARCSEC = 0.059


def _smooth(a, k):
    ny, nx = a.shape
    f = np.fft.rfft2(a)
    ky, kx = np.fft.fftfreq(ny)[:, None], np.fft.rfftfreq(nx)[None, :]
    return np.fft.irfft2(f * np.exp(-(ky ** 2 + kx ** 2) * (k * np.pi) ** 2 / 2), s=(ny, nx)).astype(np.float32)


def fov_mask(ny, nx, angle_deg=12.0, margin=0.12):
    """True inside a square field of view rotated by angle_deg and shrunk by margin: outside is padding."""
    y, x = np.mgrid[0:ny, 0:nx].astype(np.float32)
    cy, cx = (ny - 1) / 2, (nx - 1) / 2
    a = np.deg2rad(angle_deg)
    u = (x - cx) * np.cos(a) + (y - cy) * np.sin(a)
    v = -(x - cx) * np.sin(a) + (y - cy) * np.cos(a)
    half = (1 - margin) * min(ny, nx) / 2
    return (np.abs(u) <= half) & (np.abs(v) <= half)


def tunings_A(nl, isolated=True):
    """Tuning offsets from line centre, Angstrom: nl-1 across the line and one continuum far in the red wing;
    isolated=False: all nl evenly from the blue wing to that continuum, none apart."""
    if not isolated:
        return np.linspace(-0.35, 0.70, nl)
    if nl < 3:
        return np.linspace(-0.35, 0.35, nl)
    return np.concatenate([np.linspace(-0.35, 0.35, nl - 1), [0.70]])


def wcs_table(shape, isolated=True):
    """(nt, nl, 2, 2, 4) float64: HPLN, HPLT (arcsec), WAVE (nm), TIME (s since DATEREF) at the field's corners."""
    nt, _, nl, ny, nx = shape
    lam = LINE_NM + tunings_A(nl, isolated) / 10.0
    tab = np.empty((nt, nl, 2, 2, 4))
    for t in range(nt):
        cx, cy = -700.0 + 0.05 * t, 248.0 - 0.03 * t   # pointing drifts with t
        rot = np.deg2rad(0.2 * t)
        for j, py in enumerate((0, ny - 1)):
            for i, px in enumerate((0, nx - 1)):
                dx, dy = (px - (nx - 1) / 2) * PIXEL_ARCSEC, (py - (ny - 1) / 2) * PIXEL_ARCSEC
                tab[t, :, j, i, 0] = cx + dx * np.cos(rot) - dy * np.sin(rot)
                tab[t, :, j, i, 1] = cy + dx * np.sin(rot) + dy * np.cos(rot)
        tab[t, :, :, :, 2] = lam[:, None, None]
        tab[t, :, :, :, 3] = (T0_S + t * CADENCE_S + np.arange(nl) * TUNING_S)[:, None, None]
    return tab


def _primary_header(shape, continuum=True):
    from astropy.io import fits

    nt, ns, nl, ny, nx = shape
    h = fits.Header()
    h["SIMPLE"] = True
    h["BITPIX"] = -32
    h["NAXIS"] = 5
    for i, n in enumerate((nx, ny, nl, ns, nt), 1):
        h[f"NAXIS{i}"] = n
    h["EXTEND"] = True
    for i, (c, u) in enumerate((("HPLN-TAB", "arcsec"), ("HPLT-TAB", "arcsec"), ("WAVE-TAB", "nm"),
                                ("STOKES", None), ("UTC--TAB", "s")), 1):
        h[f"CTYPE{i}"] = c
        if u:
            h[f"CUNIT{i}"] = u
    for i, extra in ((1, "HPLN-INDEX"), (2, "HPLT-INDEX"), (3, None), (5, None)):
        h[f"PS{i}_0"] = "WCS-TAB"
        h[f"PS{i}_1"] = "HPLN+HPLT+WAVE+TIME"
        if extra:
            h[f"PS{i}_2"] = extra
    h["BUNIT"] = "W m^-2 Hz^-1 sr^-1"
    h["WAVEBAND"] = "Fe I 6173"
    h["DATEREF"] = f"{DATE}T00:00:00.000000"
    h["SOLARNET"] = 1.0
    if continuum:
        h["PRSTEP1"] = "STOKES-CROSSTALK-CORRECTION"
        h["PRPARA1"] = json.dumps({"TUNING_SELECTION": [nl - 1], "MARGIN": 50}, separators=(",", ":"))
    h["ORIGIN"] = "explorer synthetic cube"
    h["SYNTHVER"] = (SYNTH_VERSION, "explorer.testing.synth version")
    return h


def write_stokes_cube(path, shape=DEFAULT_SHAPE, seed=0, padding=True, continuum=True):
    """Write the _im cube with its WCS-TAB extension, one t at a time: memory ~ one t (10 MB for the default).
    continuum=False: nothing says which tuning is the continuum, as in an LP icube: no PRPARA in the header, and the
    tunings evenly spaced, none apart (tunings_A)."""
    from astropy.io import fits

    nt, ns, nl, ny, nx = shape
    if ns not in (1, 4):
        raise ValueError("ns must be 1 (I) or 4 (I, Q, U, V)")
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:ny, 0:nx].astype(np.float32)
    sy, sx, py, px = 0.51 * ny, 0.39 * nx, 0.35 * ny, 0.72 * nx
    spot = np.exp(-(((x - sx) ** 2 + (y - sy) ** 2) / (0.12 * nx) ** 2))
    pore = np.exp(-(((x - px) ** 2 + (y - py) ** 2) / (0.05 * nx) ** 2))
    b = spot - 0.8 * pore                                   # signed field, arbitrary units
    azimuth = 2 * np.arctan2(y - sy, x - sx)
    lam = tunings_A(nl, isolated=continuum).astype(np.float32)
    inside = fov_mask(ny, nx) if padding else np.ones((ny, nx), bool)
    hdr = _primary_header(shape, continuum)
    hdr["SYNTSEED"] = (seed, "random seed")

    out = fits.StreamingHDU(str(path), hdr)                 # writes the header now, data as it comes
    try:
        for t in range(nt):
            gran = _smooth(rng.standard_normal((ny, nx)).astype(np.float32), 4)
            cont = (1 + 0.08 * gran / gran.std()) * (1 - 0.75 * spot - 0.5 * pore)
            v0 = _smooth(rng.standard_normal((ny, nx)).astype(np.float32), 8)
            v0 = 0.03 * v0 / v0.std() + 0.02 * t                # Doppler shift, drifting in t
            blk = np.empty((ns, nl, ny, nx), np.float32)
            for k in range(nl):
                g = np.exp(-((lam[k] - v0) / 0.09) ** 2)
                blk[0, k] = cont * (1 - 0.6 * g)
                if ns == 4:
                    noise = rng.standard_normal((3, ny, nx)).astype(np.float32) * 0.002
                    lin = 0.004 * np.abs(b) * np.exp(-(lam[k] / 0.1) ** 2)
                    blk[1, k] = lin * np.cos(azimuth) + noise[0]
                    blk[2, k] = lin * np.sin(azimuth) + noise[1]
                    blk[3, k] = cont * 2 * (lam[k] - v0) / 0.09 ** 2 * 0.6 * g * b * 0.02 + noise[2]
            blk *= 1e-8                                     # the order of magnitude of SST intensities
            blk[:, :, ~inside] = np.nan
            out.write(blk.astype(">f4"))
    finally:
        out.close()
    tab = wcs_table(shape, isolated=continuum)
    cols = fits.ColDefs([
        fits.Column(name="HPLN+HPLT+WAVE+TIME", format=f"{tab.size}D", dim=f"(4,2,2,{nl},{nt})", array=tab[None]),
        fits.Column(name="HPLN-INDEX", format="2E", array=np.array([[1, nx]], np.float32)),
        fits.Column(name="HPLT-INDEX", format="2E", array=np.array([[1, ny]], np.float32)),
    ])
    fits.append(str(path), fits.BinTableHDU.from_columns(cols, name="WCS-TAB").data,
                fits.BinTableHDU.from_columns(cols, name="WCS-TAB").header)
    return path


def _read_im(im_path):
    from astropy.io import fits

    with fits.open(im_path, memmap=True) as h:
        return np.asarray(h[0].data)                       # big-endian float32, (t, s, l, y, x)


def write_sp_fits(im_path, sp_path, rows=64, wcs=False):
    """The per-pixel file: the _im values transposed to numpy (y, x, s, t, lambda), written rows at a time. wcs: with
    the _im's WCS-TAB extension, PSi_j keywords on its own axes and DATEREF, as SSTRED writes its _sp.fits, so that
    a reader of the header finds the times and wavelengths of the image cube in it."""
    from astropy.io import fits

    im = _read_im(im_path)
    nt, ns, nl, ny, nx = im.shape
    h = fits.Header()
    h["SIMPLE"] = True
    h["BITPIX"] = -32
    h["NAXIS"] = 5
    for i, n in enumerate((nl, nt, ns, nx, ny), 1):
        h[f"NAXIS{i}"] = n
    for i, c in enumerate(("WAVE-TAB", "UTC--TAB", "STOKES", "HPLN-TAB", "HPLT-TAB"), 1):
        h[f"CTYPE{i}"] = c
    h["BUNIT"] = "W m^-2 Hz^-1 sr^-1"
    h["ORIGIN"] = "explorer synthetic cube"
    h["SYNTHVER"] = (SYNTH_VERSION, "explorer.testing.synth version")
    if wcs:
        h.set("EXTEND", True, after="NAXIS5")
        h["DATEREF"] = f"{DATE}T00:00:00.000000"
        for i, extra in ((1, None), (2, None), (4, "HPLN-INDEX"), (5, "HPLT-INDEX")):
            h[f"PS{i}_0"] = "WCS-TAB"
            h[f"PS{i}_1"] = "HPLN+HPLT+WAVE+TIME"
            if extra:
                h[f"PS{i}_2"] = extra
    out = fits.StreamingHDU(str(sp_path), h)
    try:
        for y0 in range(0, ny, rows):
            blk = np.ascontiguousarray(im[:, :, :, y0:y0 + rows, :].transpose(3, 4, 1, 0, 2))
            out.write(blk.astype(">f4"))
    finally:
        out.close()
    if wcs:
        with fits.open(im_path) as src:
            fits.append(str(sp_path), src["WCS-TAB"].data, src["WCS-TAB"].header)
    return sp_path


def write_sp_icube(sp_fits_path, icube_path, scale=ICUBE_SCALE):
    """The integer per-pixel file (LP format) from the _sp.fits values: round(scale * value), NaN -> 0."""
    from astropy.io import fits

    with fits.open(sp_fits_path, memmap=True) as h:
        sp = np.asarray(h[0].data)                         # (y, x, s, t, l)
    ny, nx, ns, nt, nl = sp.shape
    stokes = "[I,Q,U,V]" if ns == 4 else "[I]"
    head = f"stokes={stokes}, ns={ns} :  datatype=2 (integer), dims=3, nx={nl}, ny={nt}, nt={ny * nx * ns}, endian=l"
    with open(icube_path, "wb") as f:
        f.write(head.encode("ascii").ljust(512, b"\0"))
        for y in range(ny):
            row = np.nan_to_num(sp[y].astype(np.float64) * scale, nan=0.0)
            f.write(np.clip(np.round(row), -32768, 32767).astype("<i2").tobytes())
    return icube_path


def write_lp(path, frames, head=""):
    """An LP cube without a per-pixel file, as SSTRED writes field and velocity maps: frames (nt, ny, nx) as
    little-endian float32 after a 512-byte header; head, what comes before its "datatype=" (SSTRED's "stokes=[I],
    ns=1 :  ", or " :  "). Returns path."""
    nt, ny, nx = np.shape(frames)
    with open(path, "wb") as f:
        f.write(f"{head}datatype=4 (float), dims=3, nx={nx}, ny={ny}, nt={nt}, endian=l".encode().ljust(512, b"\0"))
        f.write(np.asarray(frames).astype("<f4").tobytes())
    return path


def write_dataset(directory, name="synth_stokes", shape=DEFAULT_SHAPE, seed=0, sp=True, icube=True):
    """Write <name>_im.fits and, next to it, <name>_sp.fits and <name>_sp.icube; returns their paths."""
    os.makedirs(directory, exist_ok=True)
    paths = {"im": os.path.join(directory, f"{name}_im.fits")}
    write_stokes_cube(paths["im"], shape=shape, seed=seed)
    if sp or icube:
        paths["sp"] = write_sp_fits(paths["im"], os.path.join(directory, f"{name}_sp.fits"))
    if icube:
        paths["icube"] = write_sp_icube(paths["sp"], os.path.join(directory, f"{name}_sp.icube"))
    if not sp and "sp" in paths:
        os.remove(paths.pop("sp"))
    return paths


def write_idlsave(path, variables: dict, structures=()) -> str:
    """A minimal IDL SAVE file as SSTRED's _times+wvl.idlsave: a timestamp record (to be skipped), one VARIABLE
    record per entry, then the end marker. Values: str, numpy scalars and arrays of int16, int32, float32, float64
    or str. structures: names written as structure variables, whose bytes a reader cannot decode (they hold zeros).
    It follows the reader's view of the format: that view was checked against scipy.io.readsav on SSTRED's real
    files."""
    import struct

    def pad(b):
        return b + b"\0" * (-len(b) % 4)

    def string(s):
        b = s.encode("latin-1")
        return struct.pack(">ii", len(b), len(b)) + pad(b) if b else struct.pack(">i", 0)

    def data(a):
        if a.dtype.kind in "UO":
            return b"".join(string(str(s)) for s in a.ravel())
        if a.dtype.itemsize == 2:                       # 16 bits in the low half of a 4-byte word
            w = np.zeros((a.size, 2), ">i2")
            w[:, 1] = a.ravel()
            return w.tobytes()
        return pad(a.astype(">" + a.dtype.str[1:]).tobytes())

    def record(kind, body, start):
        nxt = start + 16 + len(body)
        return struct.pack(">iIIi", kind, nxt & 0xFFFFFFFF, nxt >> 32, 0) + body

    codes = {"i2": 2, "i4": 3, "f4": 4, "f8": 5}
    out = bytearray(b"SR\0\4")
    out += record(10, b"\0" * 24, len(out))
    items = [(k, np.asarray(v)) for k, v in variables.items()] + [(k, None) for k in structures]
    for name, a in items:
        b = name.upper().encode()
        body = struct.pack(">i", len(b)) + pad(b)
        if a is None:
            body += struct.pack(">ii", 8, 52) + b"\0" * 64
        else:
            code = 7 if a.dtype.kind in "UO" else codes[a.dtype.str[1:]]
            if a.ndim:
                dims = list(a.shape[::-1]) + [0] * (8 - a.ndim)
                body += struct.pack(">ii", code, 4) + struct.pack(">iiiii", 8, 0, a.nbytes, a.size, a.ndim)
                body += b"\0" * 8 + struct.pack(">9i", 8, *dims)
            else:
                body += struct.pack(">ii", code, 0)
            body += struct.pack(">i", 7) + data(a.reshape(-1) if a.ndim else a.reshape(1))
        out += record(2, body, len(out))
    out += record(6, b"", len(out))
    with open(path, "wb") as f:
        f.write(out)
    return str(path)
