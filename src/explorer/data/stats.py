"""Contrast limits, round axis ranges, the random profile sample that fixes the spectra's y ranges, and Q U V's
ranges from whole frames. From the prototype's app/viewer.py (limits, nice_range, quv_amplitude_ranges,
Viewer._start_sample, _sample_job, _sample_ready, _quv_ready).
"""
import os
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .axes import Roles, frame_index
from .io import FrameReader
from .kernels import absmax_into

SAMPLE_N = 100              # profiles
CONT_SAMPLE_N = 500         # the sample of a cube of 4 Stokes whose header gives no continuum (quietest_tuning)
SAMPLE_K = 2.0              # median +- 2 robust sigma per tuning (CRISPEX: mean +- 2 stdev, crispex.pro L12519)
SAMPLE_STEP = 4             # pixels drawn on a 4-px grid: 16x fewer candidates, the same spread


def limits(img, symmetric=False, lo=1.0, hi=99.0):
    """Contrast limits from the [::8, ::8] subsample (55 -> 1 ms on a 2k frame): the lo-hi percentiles of the
    finite, non-zero values; Q U V (symmetric) centred on zero at the hi percentile of |value|."""
    s = img[::8, ::8]
    s = s[np.isfinite(s) & (s != 0)]
    if not s.size:
        return (0.0, 1.0)
    if symmetric:
        m = float(np.percentile(np.abs(s), hi))
        return (-m, m) if m > 0 else (-1.0, 1.0)
    a, b = np.percentile(s, (lo, hi))
    return (float(a), float(b)) if b > a else (float(a), float(a) + 1.0)


def nice_range(lo, hi):
    """Range around [lo, hi] with bounds on a 1-2-5 grid of about a fifth of the span."""
    span = (hi - lo) or abs(hi) or 1.0
    raw = span / 4.0
    e = 10.0 ** np.floor(np.log10(raw))
    step = next(m * e for m in (1, 2, 5, 10) if m * e >= raw)
    return (float(np.floor(lo / step - 0.25) * step), float(np.ceil(hi / step + 0.25) * step))


# ---------------------------------------------------------------- y ranges of the spectra from a random sample
#
# Fixed per Stokes, as CRISPEX fixed them (crispex.pro L12519, L12588), rather than refitted at every rest: SAMPLE_N
# profiles at pixels drawn among the valid ones of the first image, each at its own random t, with a seed from the
# file's name (the same cube, the same ranges in every session). The cost is requests, not bytes (StorNext ~13 ms
# per small read), so all go at once: bellatrix, 6173 cube, 100 profiles: with the per-pixel file 1.25 s one after
# the other -> 0.04-0.05 s with 64 threads; without it 3.5 s -> 0.89-0.92 s (5600 reads of one value). Whole rows
# (10 x 10 pixels, 560 reads) were cheaper but off by up to 80 % in Halpha against a 2000-profile reference.

def sample_pixels(img, name, nt, n=SAMPLE_N, step=SAMPLE_STEP):
    """(ys, xs, ts) of the sample: n valid pixels of img (finite, non-zero) on a step grid and a t for each, drawn
    with a seed from the file's base name. None if img has no valid pixel."""
    ok = np.isfinite(img[::step, ::step]) & (img[::step, ::step] != 0)
    flat = np.flatnonzero(ok)
    if not flat.size:
        return None
    rng = np.random.default_rng(zlib.crc32(os.path.basename(str(name)).encode()))
    pick = rng.choice(flat, size=min(n, flat.size), replace=False)
    ys, xs = np.unravel_index(pick, ok.shape)
    ts = rng.integers(0, max(1, nt), size=len(pick))
    return ys * step, xs * step, ts


def sample_profiles(ys, xs, ts, frames: FrameReader, roles: Roles, pixel=None, threads: int = 16):
    """(n, ns, nl) float64 profiles at (ys, xs), each at its own t. With a per-pixel reader, one read per pixel on
    `threads` threads; else one value per (pixel, Stokes, lambda) in a single gather (call it on the numba thread)."""
    n = len(ys)
    if pixel is not None:
        with ThreadPoolExecutor(max(1, min(threads, n))) as ex:
            blocks = list(ex.map(lambda i: pixel.strip_read(int(ys[i]), int(xs[i]), 1)[0], range(n)))
        return np.stack([b[:, int(t), :] for b, t in zip(blocks, ts, strict=True)]).astype(np.float64)
    lead = frames.shape[:-2]
    if len(lead) != sum(a is not None for a in (roles.t, roles.s, roles.l)):
        raise ValueError(f"a sample needs every leading axis to be t, Stokes or lambda: {frames.layout.axes}")
    strides = frames.strides
    base = np.zeros(n, np.int64)                                       # frame number of each pixel's t
    if roles.t is not None:
        base = np.asarray(ts, np.int64) * strides[roles.t]
    sl = np.zeros((roles.ns, roles.nl), np.int64)
    if roles.s is not None:
        sl = sl + np.arange(roles.ns, dtype=np.int64)[:, None] * strides[roles.s]
    if roles.l is not None:
        sl = sl + np.arange(roles.nl, dtype=np.int64)[None, :] * strides[roles.l]
    return frames.points(ys, xs, base[:, None, None] + sl[None]).astype(np.float64)


def quietest_tuning(prof) -> int | None:
    """The tuning with the least polarisation over a sample of profiles (n, 4, nl), as read: per tuning
    sqrt(std(Q/I)^2 + std(U/I)^2 + std(V/I)^2) across the profiles, each Stokes over I at the same tuning. A profile
    counts at a tuning where its four values are finite and I > 0. The continuum of a cube whose header gives none,
    for Q U V in % of I_c: by eye, not precise (6173 icube, bellatrix: 100 profiles flipped among tunings 26, 24, 1
    and 0, 1000 gave 26 or 1, the four lowest within 0.65-0.84 % on whole frames, the line core 3.4 %). None without 4
    Stokes, with one tuning, or no tuning with 2 profiles that count."""
    prof = np.asarray(prof, dtype=np.float64)
    if prof.ndim != 3 or prof.shape[1] != 4 or prof.shape[2] < 2:
        return None
    i = prof[:, 0, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        ok = np.all(np.isfinite(prof), axis=1) & (i > 0)                # (n, nl)
        r = np.where(ok[:, None, :], prof[:, 1:, :] / np.where(ok, i, 1.0)[:, None, :], np.nan)
    n = ok.sum(axis=0)
    mean = np.nansum(r, axis=0) / np.maximum(n, 1)                      # (3, nl), NaN-safe without warnings
    var = np.nansum((r - mean) ** 2, axis=0) / np.maximum(n - 1, 1)
    score = np.sqrt(var.sum(axis=0))
    score[n < 2] = np.inf
    return int(np.argmin(score)) if np.isfinite(score).any() else None


def sample_ranges(prof, cont, iscale=None, k_sig=SAMPLE_K, intensity_rules=True):
    """Per Stokes (lo, hi) in the plots' units from the sample: I over iscale, Q U V in % of each profile's I_c when
    the continuum tuning is known (else over iscale); per tuning the median +- k_sig robust sigmas (1.4826 MAD)
    across the profiles, then the lowest and highest over lambda, on a 1-2-5 grid. I starts at 0 or above (an
    intensity; median - 2 sigma went below zero in Halpha); Q U V are symmetric about 0. Profiles with padding at
    their t are dropped first (the field moves with t). iscale, when None, is the power of ten of the median I.
    Returns (ranges, iscale, profiles kept); ranges None if no profile is left. intensity_rules False (planes that
    are no Stokes: an inversion's parameters, a snapshot's variables): every plane as read, its own range, no
    iscale."""
    prof = np.asarray(prof, dtype=np.float64)
    ns = prof.shape[1]
    intensity = prof[:, 0, :]
    keep = np.all(np.isfinite(prof), axis=(1, 2))
    if intensity_rules:
        keep &= np.all(intensity > 0, axis=1)
    prof = prof[keep]
    if not len(prof):
        return None, iscale, 0
    if not intensity_rules:
        ranges = []
        for k in range(ns):
            y = prof[:, k, :]
            med = np.median(y, axis=0)
            sig = 1.4826 * np.median(np.abs(y - med), axis=0)
            ranges.append(nice_range(float(np.min(med - k_sig * sig)), float(np.max(med + k_sig * sig))))
        return ranges, iscale, int(keep.sum())
    if iscale is None:
        iscale = float(10.0 ** np.floor(np.log10(np.median(prof[:, 0]))))
    sc = iscale or 1.0
    ranges = []
    for k in range(ns):
        y = prof[:, k, :]
        if k > 0 and cont is not None and ns > 1:
            y = 100.0 * y / prof[:, 0, cont][:, None]
        else:
            y = y / sc
        med = np.median(y, axis=0)
        sig = 1.4826 * np.median(np.abs(y - med), axis=0)
        lo, hi = float(np.min(med - k_sig * sig)), float(np.max(med + k_sig * sig))
        if k == 0 or ns == 1:
            r = nice_range(lo, hi)
            if r[0] < 0:
                r = (0.0, r[1])
        else:
            m = max(abs(lo), abs(hi)) or 1.0
            r = nice_range(-m, m)
        ranges.append(r)
    return ranges, iscale, int(keep.sum())


# ---------------------------------------------------------------- Q U V ranges from whole frames
#
# The signal of Q U V sits in a few places and in the lobes only, so a median and a MAD over profiles measure the
# noise: Q/U came out +-2 % and clipped 95-100 % of the pixels with signal (6173 cube, whole frames at 3 t). 100
# random profiles hold ~25 with signal and their p95 swung 6-14 % over seeds; whole frames are ~3 M pixels, no
# sampling noise. Not at start: while it ran (~1.2 s) the cursor went 14.8 -> 18.5-19.3 ms (bellatrix).

QUV_THREADS = 16            # frames read at once: 6173, bellatrix, unread: 0.73-1.2 s with 8, 0.67-0.76 with 16
QUV_BATCH_MB = 256          # and at most this many MB of them in memory


def quv_threads(frame_bytes: int, gather_threads: int) -> int:
    """Frames read at once for quv_amplitude_ranges: QUV_THREADS, within the probe's threads and QUV_BATCH_MB."""
    frame_mb = frame_bytes / 2 ** 20
    return max(1, min(QUV_THREADS, gather_threads, int(QUV_BATCH_MB // max(frame_mb, 1e-3))))


def quv_amplitude_ranges(frames: FrameReader, roles: Roles, cont, t, threads=8, k_sig=5.0, pct=95.0, min_px=200,
                         floor=4.0, lams=None, qu_shared=True, strips: ThreadPoolExecutor | None = None,
                         parts: int = 1):
    """Half-widths of the fixed y ranges of Q U V from the whole frames at time t. Per Stokes: A = max over lambda of
    |S| per pixel (each pixel's own lobe, wherever Zeeman splitting or Doppler shift put it; a lambda chosen from
    the mean I profile missed V's strongest by 14 %); the noise = the lowest robust sigma over lambda (the wings),
    from ~65 k pixels per frame; the pixels with A > k_sig noise have signal, and the half-width is the pct
    percentile of their A, or floor noise with fewer than min_px of them. Q and U share theirs (qu_shared): how
    the signal splits between them depends on the reference azimuth. In % of each pixel's I_c when the continuum
    tuning is known, else in the data's units. Frames are read `threads` at a time, so memory holds `threads`
    frames and one A per Stokes; byte swap, scale and maximum in one numba pass per frame (absmax_into, in strips
    on `strips`): 0.99 -> 0.44-0.49 s with the frames in the page cache (6173, bellatrix). In a cube of 4 Stokes
    a pixel where I is negative at that lambda counts nowhere (its scale 0: the negative-I rule, masking.py), from
    I's frames at each lambda (FrameReader.negative_i: one more read per lambda unless the viewer read them).
    Returns ({stokes: half-width}, {stokes: (noise, pixels with signal, percentile)}, seconds reading, total)."""
    sa = roles.s
    if sa is None:
        raise ValueError(f"Q U V ranges need a Stokes axis: {frames.layout.axes}")
    t0 = time.perf_counter()
    lay = frames.layout
    n = frames.ny * frames.nx
    converted = lay.scaled or lay.blank is not None        # integers with BSCALE/BZERO/BLANK: physical values first
    tio = [0.0]

    def read(s_, lam):
        j = frame_index(len(frames.shape) - 2, roles, t=t, s=s_, l=lam)
        q = time.perf_counter()
        b = frames.read_raw(j, chunks=1)                # one read per frame: `threads` frames run at once
        tio[0] += time.perf_counter() - q
        return frames.to_float32(b) if converted else b

    def masked(scale, s_, lam):
        """scale, 0 where I is negative at this lambda (a copy only when somewhere it is)."""
        neg = frames.negative_i(frame_index(len(frames.shape) - 2, roles, t=t, s=s_, l=lam))
        if neg is None or not neg.size:
            return scale
        out = scale.copy()
        out[neg] = 0
        return out

    dtype = np.float32 if converted else lay.dtype
    if cont is not None:
        ic = np.frombuffer(read(0, cont), dtype).astype(np.float32)
        with np.errstate(invalid="ignore", divide="ignore"):
            scale = np.where(np.isfinite(ic) & (ic > 0), np.float32(100.0) / ic, np.float32(0.0)).astype(np.float32)
    else:
        scale = np.ones(n, np.float32)
    lams = list(range(roles.nl)) if lams is None else list(lams)
    stride = max(1, n // 65536)
    half, info = {}, {}
    with ThreadPoolExecutor(max(1, threads)) as ex:
        for s_ in range(1, roles.ns):
            A = np.zeros(n, np.float32)
            noise = np.inf
            jobs = [(s_, lam) for lam in lams]
            for i in range(0, len(jobs), threads):
                got = ex.map(lambda a: (read(*a), masked(scale, *a)), jobs[i:i + threads])
                for b, sc in got:
                    sub = np.frombuffer(b, dtype)[::stride].astype(np.float32) * sc[::stride]
                    sub = sub[np.isfinite(sub) & (sub != 0)]
                    if sub.size > 100:
                        noise = min(noise, 1.4826 * float(np.median(np.abs(sub - np.median(sub)))))
                    absmax_into(A, b, dtype, sc, strips, parts)        # NaN padding never wins
            if not np.isfinite(noise) or noise <= 0:
                continue
            sig = A[A > k_sig * noise]
            p = float(np.percentile(sig, pct)) if sig.size >= min_px else float("nan")
            half[s_] = max(floor * noise, p) if np.isfinite(p) else floor * noise
            info[s_] = (noise, int(sig.size), p)
    if qu_shared and 1 in half and 2 in half:
        half[1] = half[2] = max(half[1], half[2])
    return half, info, tio[0], time.perf_counter() - t0


def quv_plot_ranges(half, cont, iscale):
    """The half-widths as symmetric plot ranges: in % of I_c with a continuum tuning, else over I's power of ten."""
    conv = 1.0 if cont is not None else 1.0 / (iscale or 1.0)
    return {k: nice_range(-m * conv, m * conv) for k, m in half.items()}


# ---------------------------------------------------------------- the noise of Q U V
#
# CRISPEX's noise level (crispex.pro L21033-21043, in CRISPEX_UPDATE_T, at every change of t): per Stokes, the
# standard deviation of S/I_c over the whole frame at the continuum tuning, pixel by pixel, NaN ignored (STDDEV(...,
# /NAN): IDL's variance divides by n - 1). Drawn at +-1 sigma (L8554-8562). Here in % of I_c, as Q U V are plotted.
# The robust sigma (1.4826 MAD) came out 7-8 % lower on the synthetic cubes (their noise the same everywhere in
# counts, so 4x wider in S/I_c over the spot's umbra) and costs 8x more: 28 against 3.7 ms for the three Stokes on
# 768 x 768 frames (Mac M-series, bench/noise_cost.py).

def stokes_noise(ic, frames: dict, robust: bool = False) -> dict[int, float]:
    """{Stokes: sigma} of frames[s] / ic in % of I_c, over the pixels where both are finite and I_c > 0: ic is
    Stokes I's frame at the continuum tuning, frames {s: the frame of Stokes s at the same (t, lambda)}. robust: 1.4826
    MAD instead of the standard deviation (n - 1). A Stokes with fewer than 2 such pixels, or a sigma that is not
    finite and positive, is left out. The ratios in float32, the sums in float64: 28 ms for the three on 2k x 2k
    frames against 42 ms all in float64, the same sigma to 3e-11 (Mac M-series)."""
    ic = np.asarray(ic, dtype=np.float32)
    out: dict[int, float] = {}
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        good = np.isfinite(ic) & (ic > 0)
        icg = ic[good]
        for s, f in frames.items():
            r = np.asarray(f, dtype=np.float32)[good] / icg
            r = r[np.isfinite(r)]
            if r.size < 2:
                continue
            if robust:
                sig = 100.0 * 1.4826 * float(np.median(np.abs(r - np.median(r))))
            else:
                sig = 100.0 * float(r.std(ddof=1, dtype=np.float64))
            if np.isfinite(sig) and sig > 0:
                out[int(s)] = sig
    return out
