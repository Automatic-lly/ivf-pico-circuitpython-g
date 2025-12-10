"""Key mapping tables for the master HID controller."""
from adafruit_hid.keycode import Keycode

# Local encoder/key bindings
LOCAL_JOY_KEYS = {
    "x+": Keycode.RIGHT_ARROW,
    "x-": Keycode.LEFT_ARROW,
    "y+": Keycode.UP_ARROW,
    "y-": Keycode.DOWN_ARROW,
    "twist+": Keycode.TAB,
    "twist-": Keycode.SHIFT,
}

LOCAL_DUAL_KEYS = {
    "x+": Keycode.ONE,
    "x-": Keycode.TWO,
    "y+": Keycode.THREE,
    "y-": Keycode.FOUR,
}

LOCAL_SINGLE_KEYS = {
    "+": Keycode.FIVE,
    "-": Keycode.SIX,
}

# Remote encoder/key bindings received over UART
REMOTE_JOY_KEYS = {
    "x+": Keycode.D,
    "x-": Keycode.A,
    "y+": Keycode.W,
    "y-": Keycode.S,
    "twist+": Keycode.Q,
    "twist-": Keycode.E,
}

REMOTE_DUAL_KEYS = {
    0: {
        "x+": Keycode.Z,
        "x-": Keycode.X,
        "y+": Keycode.C,
        "y-": Keycode.V,
    },
    1: {
        "x+": Keycode.B,
        "x-": Keycode.N,
        "y+": Keycode.M,
        "y-": Keycode.COMMA,
    },
}

REMOTE_SINGLE_KEYS = {
    "+": Keycode.SEVEN,
    "-": Keycode.EIGHT,
}
