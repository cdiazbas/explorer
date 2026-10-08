"""Linking cubes to the first one (ROADMAP E8.1, data.link), without a screen: a map whose frames nothing names
links as the first cube's times when it has as many, as a still image with one, and is refused with another number;
another grid is refused; a cube with its own axes and the same times links as it reads; times are the same within
half the first cube's cadence, and an LP cube's times of day compare as such. Each test prints what it decided."""
import numpy as np
import pytest

from explorer.testing import synth

SHAPE = (6, 4, 21, 48, 40)                              # t, s, lambda, y, x


@pytest.fixture(scope="module")
def cubes(tmp_path_factory):
    d = tmp_path_factory.mktemp("link")
    main = synth.write_dataset(d, "main", shape=SHAPE, sp=False, icube=False)["im"]
    twin = synth.write_dataset(d, "twin", shape=SHAPE, seed=3, sp=False, icube=False)["im"]
    return d, main, twin


def lp_map(directory, name, n, ny=SHAPE[3], nx=SHAPE[4]):
    """An LP map as SSTRED writes field and velocity maps: n frames, and no scans in its name to say what they are."""
    path = directory / name
    head = f"datatype=4 (float), dims=3, nx={nx}, ny={ny}, nt={n}, endian=l".encode().ljust(512, b"\0")
    with open(path, "wb") as f:
        f.write(head)
        f.write(np.random.default_rng(n).normal(size=(n, ny, nx)).astype("<f4").tobytes())
    return path


def show(link):
    print(f"{link.path.split('/')[-1]}: ok={link.ok} axes={link.axes!r} how={link.how!r} why={link.why!r}")


def test_a_map_with_as_many_frames_as_times_follows_them(cubes):
    from explorer.data.link import describe, plan

    d, main, _ = cubes
    path = lp_map(d, "Blos.map.fcube", SHAPE[0])
    alone = describe(path).roles
    print("on its own:", alone)                         # nothing names its frames: read as an unknown profile axis
    assert alone.how == "unknown" and alone.t is None
    link = plan(describe(main), path)
    show(link)
    assert link.ok and link.axes == "t" and "times" in link.how
    info = describe(link.path, link.axes)
    assert (info.roles.t, info.roles.nt, info.roles.l) == (0, SHAPE[0], None)


def test_one_frame_is_shown_at_every_t(cubes):
    from explorer.data.link import describe, plan

    d, main, _ = cubes
    link = plan(describe(main), lp_map(d, "context.fcube", 1))
    show(link)
    assert link.ok and "every t" in link.how


def test_another_number_of_unnamed_frames_is_refused_with_what_would_do(cubes):
    from explorer.data.link import describe, plan

    d, main, _ = cubes
    link = plan(describe(main), lp_map(d, "Bstr.map.fcube", 4))
    show(link)
    assert not link.ok and "4 frames" in link.why and f"{SHAPE[0]} times" in link.why and "--axes" in link.why


def test_another_grid_is_refused(cubes):
    from explorer.data.link import describe, plan

    d, main, _ = cubes
    link = plan(describe(main), lp_map(d, "wide.fcube", SHAPE[0], nx=SHAPE[4] + 1))
    show(link)
    assert not link.ok and "pixels" in link.why and "grids" in link.why


def test_a_cube_with_its_own_axes_and_the_same_times_links_as_it_reads(cubes):
    from explorer.data.dataset import Dataset
    from explorer.data.link import plan

    _, main, twin = cubes
    with Dataset.open(main) as m:                       # a Dataset leads as well as a CubeInfo
        link = plan(m, twin)
    show(link)
    assert link.ok and link.axes is None and "same times" in link.how


def test_times_are_matched_by_the_nearest():
    from explorer.data.axes import Axes
    from explorer.data.link import frames

    def ax(t, day=None):
        a = Axes()
        a.t_sec = np.asarray(t, float)
        if day is None:
            a.time_of_day = True
        else:
            a.dateref = np.datetime64(day)
        return a

    t = np.arange(6) * 20.0 + 30000.0                    # 20-s cadence, times of day
    cases = {
        "the same, LP": frames(ax(t), ax(t + 3.0), 6, 6),
        "half a cadence off": frames(ax(t), ax(t + 11.0), 6, 6),
        "another number": frames(ax(t), ax(t[:4]), 6, 4),
        "another day": frames(ax(t, "2025-07-11T00:00:00"), ax(t, "2025-07-12T00:00:00"), 6, 6),
        "FITS against LP": frames(ax(t - 3600.0, "2025-07-11T01:00:00"), ax(t), 6, 6),
        "no times of its own": frames(ax(t), Axes(), 6, 6),
        "no times of its own, another number": frames(ax(t), Axes(), 6, 4),
        "one frame": frames(ax(t), Axes(), 6, 1),
    }
    for k, v in cases.items():
        print(f"{k}: t={None if v.t is None else v.t.tolist()} dt={None if v.dt is None else v.dt.tolist()} "
              f"{v.note!r}")
    got = {k: None if v.t is None else v.t.tolist() for k, v in cases.items()}
    assert got["the same, LP"] == got["FITS against LP"] == got["no times of its own"] == [0, 1, 2, 3, 4, 5]
    assert got["half a cadence off"] == [0, 0, 1, 2, 3, 4]       # 11 s after: the scan before is 9 s away
    assert got["another number"] == [0, 1, 2, 3, 3, 3] and "2 of the 6 times" in cases["another number"].note
    assert got["another day"] is None and got["no times of its own, another number"] is None
    assert got["one frame"] == [0] * 6
    assert "same times" in cases["the same, LP"].note


# ---------------------------------------------------------------- other cadences (ROADMAP E8.4)

CAD = (55, 1, 3, 16, 12)                                 # the first cube: 55 scans at synth.CADENCE_S (20 s)
FIRST = synth.T0_S + 0.25 + np.arange(55) * synth.CADENCE_S      # its scans' times (the mean over its tunings)
SECOND = FIRST[-1] + 400.0 + np.arange(1, 30) * synth.CADENCE_S   # a second series 400 s after its last scan


def lp_stokes_i(directory, stem, scans, times=True):
    """An LP Stokes I cube of the scans (times of day, s), named as SSTRED names one (a cube joined from two series
    has both ranges in its name), each frame holding its scan number, with its times in the full-Stokes cube's file
    (it has none of its own); without times, no file at all."""
    nt, nl, ny, nx = len(scans), CAD[2], CAD[3], CAD[4]
    path = directory / f"{stem}_stokesI_corrected_im.aligned6173.icube"
    head = f"stokes=[I], ns=1 :  datatype=2 (integer), dims=3, nx={nx}, ny={ny}, nt={nt * nl}, endian=l"
    path.write_bytes(head.encode().ljust(512, b"\0") + np.repeat(np.arange(nt, dtype="<i2"), nl * ny * nx).tobytes())
    if times:
        tod = np.asarray(scans)[:, None] + (np.arange(nl) - 1) * 0.25    # (scan, tuning), their mean the scan's
        synth.write_idlsave(directory / f"{stem}_stokes_corrected_im_times+wvl.idlsave",
                            {"lambda": np.array([854.04, 854.21, 854.40]), "time": tod,
                             "fac": np.float32(1.0), "nan_rplcmnt": np.float32(-1.7691475e-08)})
    return path


@pytest.fixture(scope="module")
def cadences(tmp_path_factory):
    """The first cube (FITS, 55 scans); an LP cube of 84 scans in two series, the first 55 scans 6 s after the first
    cube's (as 8542 after 6173 in one SST sequence); one of the second series alone; one 14 s after (more than half
    the 20-s cadence: the scan before is nearer); the 84 again, without times."""
    d = tmp_path_factory.mktemp("cadence")
    for sub in ("second", "late", "bare"):
        (d / sub).mkdir()
    return {"main": synth.write_stokes_cube(d / "nb_6173_=0-54_stokes_corrected_im.fits", shape=CAD),
            "84": lp_stokes_i(d, "nb_8542_=0-54_=0-28", np.concatenate([FIRST + 6.0, SECOND + 6.0])),
            "second": lp_stokes_i(d / "second", "nb_8542_=0-28", SECOND + 6.0),
            "late": lp_stokes_i(d / "late", "nb_8542_=0-54", FIRST + 14.0),
            "bare": lp_stokes_i(d / "bare", "nb_8542_=0-54_=0-28", np.zeros(84), times=False)}


def test_another_cadence_links_by_the_nearest_time(cadences):
    from explorer.data.link import describe, plan

    link = plan(describe(cadences["main"]), cadences["84"])
    show(link)
    assert link.ok and "nearest" in link.how
    back = plan(describe(cadences["84"]), cadences["main"])        # the 84 lead: its last 29 are far from any
    show(back)
    assert back.ok and "29 of the 84 times" in back.how


def test_a_cube_without_times_is_still_refused_at_another_cadence(cadences):
    from explorer.data.link import describe, plan

    link = plan(describe(cadences["main"]), cadences["bare"])
    show(link)
    assert not link.ok and "84 times against 55" in link.why and "no times" in link.why


def _shown(lead, other, nt):
    """The t of other shown at each t of lead, as the session gives it to its reads; the image at the last."""
    from explorer.core.loop import ManualLoop
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset

    with Dataset.open(lead, no_sp=True) as m, Dataset.open(other, no_sp=True, executors=m.executors) as o:
        s = Session(ManualLoop(), m)
        k = s.add(o)
        got = []
        for t in range(nt):
            s.set_index("t", t)
            got.append(s.member_state(k).t)
        img = o.image(s.index(k)).result(5) if o.layout.kind == "lp" else None
    return got, img


def test_the_nearest_frame_of_each_linked_cube_at_each_t(cadences):
    from explorer.core.loop import ManualLoop
    from explorer.core.session import Session
    from explorer.data.dataset import Dataset

    cases = {"6173 leads (55), 8542 of 84 shows": (cadences["main"], cadences["84"], 55, list(range(55))),
             "8542 of 84 leads, 6173 (55) shows": (cadences["84"], cadences["main"], 84,
                                                   list(range(55)) + [54] * 29),
             "8542 of 84 leads, the second series (29) shows": (cadences["84"], cadences["second"], 84,
                                                                [0] * 55 + list(range(29))),
             "6173 leads, 8542 14 s after each scan shows": (cadences["main"], cadences["late"], 55,
                                                            [0] + list(range(54)))}
    for name, (lead, other, nt, want) in cases.items():
        got, img = _shown(lead, other, nt)
        print(f"{name}: {got}")
        assert got == want, name
        if img is not None:                              # the frame read is the one of that scan
            assert (img == want[-1]).all()
    with Dataset.open(cadences["main"], no_sp=True) as m, \
            Dataset.open(cadences["bare"], no_sp=True, executors=m.executors) as b:
        with pytest.raises(ValueError, match="no times"):
            Session(ManualLoop(), m).add(b)
