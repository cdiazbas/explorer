"""Small synthetic Stokes cubes, deterministic, shaped like SST reduced data: numpy (t, s, lambda, y, x), big-endian
float32 (standard FITS), and NaN padding around a rotated field of view.

The padding matters: the prototype's first synthetic cube had none and hid a colour bug that real data showed at once.
Physics is only plausible (granulation, a spot and a pore, an absorption line with a Doppler shift that drifts in
t, V antisymmetric in lambda, Q and U from the spot's azimuth), enough for every panel to show structure.

The header has CTYPE, BUNIT and DATE-OBS but not yet the SOLARNET WCS-TAB tables of real cubes (ROADMAP E0.6).
"""
import numpy as np

SYNTH_VERSION = 1                       # bump when the content changes: cached demo cubes are then rewritten
DEFAULT_SHAPE = (8, 4, 10, 256, 256)    # (t, s, lambda, y, x): 84 MB


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


def write_stokes_cube(path, shape=DEFAULT_SHAPE, seed=0, padding=True):
    """Write the cube to path (overwriting), one t at a time: memory ~ one t (10 MB for the default shape)."""
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
    lam = np.linspace(-0.35, 0.35, nl).astype(np.float32)   # Angstrom from line centre
    inside = fov_mask(ny, nx) if padding else np.ones((ny, nx), bool)

    hdr = fits.Header()
    hdr["SIMPLE"] = True
    hdr["BITPIX"] = -32
    hdr["NAXIS"] = 5
    for i, (n, c) in enumerate(((nx, "HPLN-TAN"), (ny, "HPLT-TAN"), (nl, "WAVE"), (ns, "STOKES"), (nt, "UTC")), 1):
        hdr[f"NAXIS{i}"] = n
        hdr[f"CTYPE{i}"] = c
    hdr["BUNIT"] = "W m^-2 Hz^-1 sr^-1"
    hdr["DATE-OBS"] = "2025-07-11T08:16:57"
    hdr["ORIGIN"] = "explorer synthetic cube"
    hdr["SYNTHVER"] = (SYNTH_VERSION, "explorer.testing.synth version")
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
    return path
