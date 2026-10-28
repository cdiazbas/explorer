"""The numbers under a colour key (ui.overlays.limits_text, the image's key and the 2x2 panels' keys): enough
digits for its two limits to differ, as few as before where two significant figures tell them apart."""


def test_the_key_s_limits_have_the_digits_to_differ():
    """A key's two limits differ where the values do ("4.19", "4.22", not "4.2" twice); where two
    significant figures tell them apart, as before."""
    from explorer.ui.overlays import limits_text

    got = [limits_text(4.19, 4.22), limits_text(4.2, 4.2), limits_text(1.9, 10.0), limits_text(-0.31, 0.31),
           limits_text(1016.2, 1016.4)]
    print(got)
    assert got == [("4.19", "4.22"), ("4.2", "4.2"), ("1.9", "10"), ("−0.31", "0.31"), ("1016.2", "1016.4")]


def test_a_key_at_rest_signs_its_upper_limit_only_across_0():
    """At rest, "+" before the upper limit where the bar spans 0; two limits of one sign without it (log₁₀(p) of a
    Bifrost snapshot, −3.3 … −1.3, read "+−1.3"). Before: "+" whenever the lower limit was negative."""
    from explorer.ui.overlays import rest_numbers

    got = [rest_numbers(-3.3, -1.3), rest_numbers(-0.31, 0.31), rest_numbers(1.0, 2.0), rest_numbers(-1.0, 0.0)]
    print(got)
    assert got == [("−3.3", "−1.3"), ("−0.31", "+0.31"), ("1", "2"), ("−1", "0")]


def test_the_zero_mark_is_written_only_where_it_fits_between_the_limits():
    """The "0" of a key at rest, between the two limits' numbers with a gap: in the middle of a symmetric bar it
    fits; near a limit (limits of its own on each side, key Z) or on a bar too narrow, it is left out, as it ran into
    the lower number. Before: always written."""
    from explorer.ui.overlays import ZERO_GAP, zero_fits

    lo_w, zero_w, hi_w = 22, 6, 24
    mid = zero_fits(60, 0, 120, lo_w, zero_w, hi_w)
    near = zero_fits(lo_w + 2, 0, 120, lo_w, zero_w, hi_w)
    narrow = zero_fits(30, 0, 60, lo_w, zero_w, hi_w)
    edge = zero_fits(lo_w + ZERO_GAP + zero_w / 2, 0, 120, lo_w, zero_w, hi_w)
    print("mid", mid, "near", near, "narrow", narrow, "just fits", edge)
    assert mid and not near and not narrow and edge
