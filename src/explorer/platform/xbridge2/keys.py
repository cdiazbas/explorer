"""X keyboard to Qt keys, without Qt: which keysym a key press means (the core protocol's rules: groups, Shift,
Caps Lock, Num Lock), the Qt key and text for it, and the modifiers of an X state. Qt keys are named here and turned
into Qt's values by the input module.

python-xlib and this module read the core keyboard mapping only (no XKB): the X server presents its layout there,
with the second group behind Mode_switch (XQuartz's Option key) and, on XKB servers, the third level behind
ISO_Level3_Shift (AltGr) in keysyms 5 and 6 of each key.
"""
import struct
from dataclasses import dataclass, field

NO_SYMBOL = 0
MOD_SHIFT, MOD_LOCK, MOD_CONTROL = 1, 2, 4

# keysyms that are not characters -> Qt key names (the prototype's table, audit F15, F20f)
SPECIAL = {0xFF08: "Key_Backspace", 0xFF09: "Key_Tab", 0xFF0D: "Key_Return", 0xFF1B: "Key_Escape",
           0xFFFF: "Key_Delete", 0xFF50: "Key_Home", 0xFF51: "Key_Left", 0xFF52: "Key_Up", 0xFF53: "Key_Right",
           0xFF54: "Key_Down", 0xFF55: "Key_PageUp", 0xFF56: "Key_PageDown", 0xFF57: "Key_End",
           0xFF8D: "Key_Enter", 0xFF63: "Key_Insert", 0xFE20: "Key_Backtab", 0xFF67: "Key_Menu", 0xFF6A: "Key_Help",
           0xFF61: "Key_Print", 0xFF13: "Key_Pause", 0xFF14: "Key_ScrollLock", 0xFF15: "Key_SysReq",
           0xFF0B: "Key_Clear", 0xFFE1: "Key_Shift", 0xFFE2: "Key_Shift", 0xFFE3: "Key_Control",
           0xFFE4: "Key_Control", 0xFFE7: "Key_Meta", 0xFFE8: "Key_Meta", 0xFFE9: "Key_Alt", 0xFFEA: "Key_Alt",
           0xFFEB: "Key_Super_L", 0xFFEC: "Key_Super_R", 0xFFED: "Key_Hyper_L", 0xFFEE: "Key_Hyper_R",
           0xFFE5: "Key_CapsLock", 0xFF7F: "Key_NumLock", 0xFE03: "Key_AltGr", 0xFF7E: "Key_Mode_switch"}
SPECIAL.update({0xFFBE + i: f"Key_F{i + 1}" for i in range(35)})
# the keypad without Num Lock: the same keys as the main block
SPECIAL.update({0xFF95: "Key_Home", 0xFF96: "Key_Left", 0xFF97: "Key_Up", 0xFF98: "Key_Right", 0xFF99: "Key_Down",
                0xFF9A: "Key_PageUp", 0xFF9B: "Key_PageDown", 0xFF9C: "Key_End", 0xFF9F: "Key_Delete",
                0xFF9E: "Key_Insert", 0xFF9D: "Key_Clear", 0xFF89: "Key_Tab", 0xFF80: "Key_Space"})
# the keypad with Num Lock: digits and operators, with their text
SPECIAL.update({0xFFB0 + i: f"Key_{i}" for i in range(10)})
SPECIAL.update({0xFFAA: "Key_Asterisk", 0xFFAB: "Key_Plus", 0xFFAD: "Key_Minus", 0xFFAE: "Key_Period",
                0xFFAF: "Key_Slash", 0xFFAC: "Key_Comma", 0xFFBD: "Key_Equal"})
# the text xkb gives these keys (xcb passes it on: Return is "\r", not "")
TEXT = {0xFF08: "\x08", 0xFF09: "\t", 0xFF0D: "\r", 0xFF1B: "\x1b", 0xFFFF: "\x7f", 0xFF8D: "\r", 0xFE20: "\t",
        0xFF89: "\t", 0xFF80: " ", 0xFFAA: "*", 0xFFAB: "+", 0xFFAD: "-", 0xFFAE: ".", 0xFFAF: "/", 0xFFAC: ",",
        0xFFBD: "="}
TEXT.update({0xFFB0 + i: str(i) for i in range(10)})

ALT = {0xFFE9, 0xFFEA}
META = {0xFFE7, 0xFFE8, 0xFFEB, 0xFFEC, 0xFFED, 0xFFEE}
NUM_LOCK, MODE_SWITCH, LEVEL3 = 0xFF7F, 0xFF7E, 0xFE03


def is_keypad(sym: int) -> bool:
    return 0xFF80 <= sym <= 0xFFBD


def keysym_char(sym: int) -> str | None:
    """The character a keysym types: Latin-1 keysyms are their code point, 0x01000000 + c is Unicode c."""
    if 0x20 <= sym <= 0x7E or 0xA0 <= sym <= 0xFF:
        return chr(sym)
    if sym & 0xFF000000 == 0x01000000:
        cp = sym & 0xFFFFFF
        if cp <= 0x10FFFF:
            return chr(cp)
    return None


def _cased(sym: int) -> tuple[int, int]:
    """(lower, upper) keysyms of a character keysym, (sym, sym) for anything else."""
    ch = keysym_char(sym)
    if ch is None:
        return sym, sym
    lo, up = ch.lower(), ch.upper()
    if len(lo) != 1 or len(up) != 1:
        return sym, sym

    def ks(c):
        o = ord(c)
        return o if o <= 0xFF else 0x01000000 | o
    return ks(lo), ks(up)


@dataclass
class Keymap:
    """The core keyboard mapping: keysyms per keycode, and which modifier bits mean what."""
    min_keycode: int
    per_code: int
    syms: list = field(default_factory=list)            # per keycode from min_keycode, a tuple of keysyms
    alt: int = 8                                        # Mod1, unless the modifier map says otherwise
    meta: int = 64                                      # Mod4
    num_lock: int = 16                                  # Mod2
    mode_switch: int = 0
    level3: int = 0

    @classmethod
    def from_replies(cls, min_keycode: int, kbd: bytes, mods: bytes | None) -> "Keymap":
        per = kbd[1]
        n = struct.unpack_from("<I", kbd, 4)[0] // max(1, per)
        vals = struct.unpack_from(f"<{n * per}I", kbd, 32)
        km = cls(min_keycode, per, [tuple(vals[i * per:(i + 1) * per]) for i in range(n)])
        if mods is not None:
            km.set_modifiers(mods)
        return km

    def set_modifiers(self, reply: bytes) -> None:
        per = reply[1]
        codes = reply[32:32 + 8 * per]
        found = {"alt": 0, "meta": 0, "num_lock": 0, "mode_switch": 0, "level3": 0}
        for i in range(8):
            for kc in codes[i * per:(i + 1) * per]:
                syms = set(self.keysyms(kc))
                if syms & ALT:
                    found["alt"] |= 1 << i
                if syms & META:
                    found["meta"] |= 1 << i
                if NUM_LOCK in syms:
                    found["num_lock"] |= 1 << i
                if MODE_SWITCH in syms:
                    found["mode_switch"] |= 1 << i
                if LEVEL3 in syms:
                    found["level3"] |= 1 << i
        for k, v in found.items():                      # the map says it: a modifier it does not have is none
            setattr(self, k, v & ~(MOD_SHIFT | MOD_LOCK | MOD_CONTROL))

    def keysyms(self, keycode: int) -> tuple:
        i = keycode - self.min_keycode
        return self.syms[i] if 0 <= i < len(self.syms) else ()

    def keysym(self, keycode: int, state: int) -> int:
        """The keysym of a key pressed with this modifier state (X11 protocol, "Keyboards")."""
        k = list(self.keysyms(keycode)) + [NO_SYMBOL] * 6
        if self.level3 and state & self.level3 and (k[4] or k[5]):
            a, b = k[4], k[5]
        elif self.mode_switch and state & self.mode_switch and (k[2] or k[3]):
            a, b = k[2], k[3]
        else:
            a, b = k[0], k[1]
        if b == NO_SYMBOL:
            lo, up = _cased(a)
            a, b = (lo, up) if lo != up else (a, a)
        shift, lock = bool(state & MOD_SHIFT), bool(state & MOD_LOCK)
        if self.num_lock and state & self.num_lock and is_keypad(b):
            return a if shift else b
        if not shift and not lock:
            return a
        if not shift and lock:
            return _cased(a)[1]
        if shift and lock:
            return _cased(b)[1]
        return b


def ctrl_char(ch: str) -> str:
    """What xkb (libxkbcommon's XkbToControl) makes of a character typed with Ctrl."""
    c = ord(ch)
    if 0x40 <= c < 0x7F or ch == " ":
        return chr(c & 0x1F)
    return {"2": "\x00", "8": "\x7f", "/": "\x1f"}.get(ch, chr(c - ord("3") + 0x1B) if "3" <= ch <= "7" else ch)


def translate(sym: int, ctrl: bool) -> tuple[str | int, str] | None:
    """(Qt key name, or the key's code for a character; text) of a keysym; None for one Qt has no key for."""
    ch = keysym_char(sym)
    if ch is not None:
        up = ch.upper()
        key = ord(up if len(up) == 1 else ch)           # Qt's key is the upper case (ß has none of one letter)
        text = ctrl_char(ch) if ctrl and ch.isascii() else ch
        return key, text
    if sym in SPECIAL:
        return SPECIAL[sym], TEXT.get(sym, "")
    return None
