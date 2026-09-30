"""X keyboard to Qt keys, no Qt: the core protocol's keysym rules and the text of each key."""
import struct

from explorer.platform.xbridge import keys as K

SHIFT, LOCK, CTRL = 1, 2, 4
MOD1, MOD2, MOD4, MOD5 = 8, 16, 64, 128


def keymap():
    km = K.Keymap(8, 4, [()] * 248)
    km.syms[38 - 8] = (ord("a"), 0, 0, 0)                          # a: one keysym, its case from the rules
    km.syms[10 - 8] = (ord("1"), ord("!"), 0, 0)
    km.syms[47 - 8] = (0xF1, 0xD1, 0, 0)                            # ñ Ñ (Latin-1)
    km.syms[24 - 8] = (ord("q"), ord("Q"), 0x40, 0)                 # group 2 behind Mode_switch: @
    km.syms[87 - 8] = (0xFF9C, 0xFFB1, 0, 0)                        # KP_End / KP_1
    km.syms[111 - 8] = (0xFF52, 0, 0, 0)                            # Up
    km.syms[50 - 8] = (0xFFE1, 0, 0, 0)                             # Shift_L
    km.syms[64 - 8] = (0xFFE9, 0, 0, 0)                             # Alt_L
    km.syms[133 - 8] = (0xFFEB, 0, 0, 0)                            # Super_L
    km.syms[77 - 8] = (0xFF7F, 0, 0, 0)                             # Num_Lock
    km.syms[92 - 8] = (0xFF7E, 0, 0, 0)                             # Mode_switch
    return km


def modmap(per=2):
    codes = [[50, 0], [0, 0], [37, 0], [64, 0], [77, 0], [0, 0], [133, 0], [92, 0]]   # shift lock ctrl mod1..mod5
    return bytes(32) + bytes(c for row in codes for c in row) if per == 2 else b""


def test_the_core_rules():
    km = keymap()
    rep = bytearray(modmap())
    rep[1] = 2
    km.set_modifiers(bytes(rep))
    assert (km.alt, km.meta, km.num_lock, km.mode_switch) == (MOD1, MOD4, MOD2, MOD5)
    a = 38
    assert km.keysym(a, 0) == ord("a") and km.keysym(a, SHIFT) == ord("A")
    assert km.keysym(a, LOCK) == ord("A") and km.keysym(a, SHIFT | LOCK) == ord("A")
    assert km.keysym(10, LOCK) == ord("1") and km.keysym(10, SHIFT) == ord("!")      # Caps Lock: letters only
    assert km.keysym(47, LOCK) == 0xD1                                               # and non-ASCII letters
    assert km.keysym(24, MOD5) == 0x40                                               # Mode_switch: group 2
    assert km.keysym(87, 0) == 0xFF9C and km.keysym(87, MOD2) == 0xFFB1              # Num Lock on the keypad
    assert km.keysym(87, MOD2 | SHIFT) == 0xFF9C


def test_translate_keys_and_text():
    assert K.translate(ord("a"), False) == (ord("A"), "a")                 # Qt's key is the upper case
    assert K.translate(ord("a"), True) == (ord("A"), "\x01")               # Ctrl+A gives "\x01", as xkb
    assert K.translate(0xF1, False) == (0xD1, "ñ")
    assert K.translate(0x01000000 | 0x3BB, False) == (0x39B, "λ")          # a Unicode keysym
    assert K.translate(0xFF0D, False) == ("Key_Return", "\r")
    assert K.translate(0xFFB1, False) == ("Key_1", "1")
    assert K.translate(0xFF52, False) == ("Key_Up", "")
    assert K.translate(0xFE50, False) is None                             # a dead key: no Qt key
    assert K.is_keypad(0xFFB1) and not K.is_keypad(0xFF52)


def test_from_server_replies():
    per, lo, n = 2, 8, 3
    syms = [ord("a"), 0, ord("b"), ord("B"), 0xFF52, 0]
    kbd = struct.pack("<BBHI24x", 1, per, 0, len(syms)) + struct.pack(f"<{len(syms)}I", *syms)
    km = K.Keymap.from_replies(lo, kbd, None)
    assert len(km.syms) == n and km.keysym(9, SHIFT) == ord("B") and km.keysym(10, 0) == 0xFF52
