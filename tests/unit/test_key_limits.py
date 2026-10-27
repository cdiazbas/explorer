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
