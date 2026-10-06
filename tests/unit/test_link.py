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


def test_times_are_the_same_within_half_the_cadence():
    from explorer.data.axes import Axes
    from explorer.data.link import same_times

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
        "the same, LP": same_times(ax(t), ax(t + 3.0)),
        "half a cadence off": same_times(ax(t), ax(t + 11.0)),
        "another number": same_times(ax(t), ax(t[:4])),
        "another day": same_times(ax(t, "2025-07-11T00:00:00"), ax(t, "2025-07-12T00:00:00")),
        "FITS against LP": same_times(ax(t - 3600.0, "2025-07-11T01:00:00"), ax(t)),
        "no times of its own": same_times(ax(t), Axes()),
    }
    for k, v in cases.items():
        print(f"{k}: {v}")
    assert cases["the same, LP"][0] and not cases["half a cadence off"][0] and not cases["another number"][0]
    assert not cases["another day"][0] and cases["FITS against LP"][0] and cases["no times of its own"][0]
