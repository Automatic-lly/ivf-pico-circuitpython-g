"""
Master controller for dual-board encoder + joystick HID system.
Runs on Raspberry Pi Pico with CircuitPython.
"""
import time
import board
import busio
import rotaryio
import usb_hid
from adafruit_hid.keyboard import Keyboard

from master_keymap import (
    LOCAL_DUAL_KEYS,
    LOCAL_JOY_KEYS,
    LOCAL_SINGLE_KEYS,
    REMOTE_DUAL_KEYS,
    REMOTE_JOY_KEYS,
    REMOTE_SINGLE_KEYS,
)

# ----------------------------- Configuration -----------------------------
UART_BAUD = 115200
UART_RX_PIN = board.GP21
RELEASE_MS = 1

# Joystick encoders (local)
JOY_PINS = {
    "x": (board.GP2, board.GP3),
    "y": (board.GP4, board.GP5),
    "twist": (board.GP6, board.GP7),
}

# Dual-axis encoder (local, index 0)
DUAL0_PINS = {
    "x": (board.GP8, board.GP9),
    "y": (board.GP10, board.GP11),
}

# Single-axis encoder (local)
SINGLE_PINS = (board.GP12, board.GP13)

# ------------------------------ Utilities -------------------------------

def now_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def tap_key(keyboard: Keyboard, key, pressed: dict) -> None:
    current = pressed.get(key)
    current_time = now_ms()
    if current:
        keyboard.release(key)
    keyboard.press(key)
    pressed[key] = current_time + RELEASE_MS


def service_key_releases(keyboard: Keyboard, pressed: dict) -> None:
    current_time = now_ms()
    to_release = [key for key, due in pressed.items() if due <= current_time]
    for key in to_release:
        keyboard.release(key)
        pressed.pop(key, None)


def process_encoder(enc: rotaryio.IncrementalEncoder, last_positions: dict, name: str, handler) -> None:
    pos = enc.position
    last = last_positions.get(name, 0)
    delta = pos - last
    if delta == 0:
        return
    step_dir = "+" if delta > 0 else "-"
    for _ in range(abs(delta)):
        handler(step_dir)
    last_positions[name] = pos


# ------------------------------ Handlers --------------------------------

def handle_local_joystick(encoders, last_positions, keyboard, pressed):
    def make_handler(prefix):
        def _handler(direction):
            key = LOCAL_JOY_KEYS.get(f"{prefix}{direction}")
            if key:
                tap_key(keyboard, key, pressed)
        return _handler

    process_encoder(encoders["x"], last_positions, "joy_x", make_handler("x"))
    process_encoder(encoders["y"], last_positions, "joy_y", make_handler("y"))
    process_encoder(encoders["twist"], last_positions, "joy_twist", make_handler("twist"))


def handle_local_dualaxis(encoders, last_positions, keyboard, pressed):
    def make_handler(prefix):
        def _handler(direction):
            key = LOCAL_DUAL_KEYS.get(f"{prefix}{direction}")
            if key:
                tap_key(keyboard, key, pressed)
        return _handler

    process_encoder(encoders["x"], last_positions, "dual0_x", make_handler("x"))
    process_encoder(encoders["y"], last_positions, "dual0_y", make_handler("y"))


def handle_local_singleaxis(encoder, last_positions, keyboard, pressed):
    def _handler(direction):
        key = LOCAL_SINGLE_KEYS.get(direction)
        if key:
            tap_key(keyboard, key, pressed)

    process_encoder(encoder, last_positions, "single", _handler)


# ----------------------------- UART Parsing -----------------------------

def apply_remote_event(kind, payload, keyboard, pressed):
    if kind == "J":
        axis, direction = payload
        key = REMOTE_JOY_KEYS.get(f"{axis}{direction}")
        if key:
            tap_key(keyboard, key, pressed)
    elif kind == "D":
        idx, axis, direction = payload
        encoder_map = REMOTE_DUAL_KEYS.get(idx, {})
        key = encoder_map.get(f"{axis}{direction}")
        if key:
            tap_key(keyboard, key, pressed)
    elif kind == "S":
        direction = payload
        key = REMOTE_SINGLE_KEYS.get(direction)
        if key:
            tap_key(keyboard, key, pressed)


def parse_uart_line(line):
    text = line.strip()
    if not text:
        return None
    if text.startswith("J") and len(text) == 3:
        axis_code = text[1]
        dir_code = text[2]
        axis_map = {"0": "x", "1": "y", "2": "twist"}
        if axis_code in axis_map and dir_code in ("+", "-"):
            return ("J", (axis_map[axis_code], dir_code))
    if text.startswith("D"):
        parts = text[1:].strip().split()
        if len(parts) == 3:
            idx, axis, direction = parts
            if idx.isdigit() and axis in ("0", "1") and direction in ("+", "-"):
                axis_label = "x" if axis == "0" else "y"
                return ("D", (int(idx), axis_label, direction))
    if text.startswith("S") and len(text) == 2:
        direction = text[1]
        if direction in ("+", "-"):
            return ("S", direction)
    return None


def handle_uart_packets(uart, keyboard, pressed, rx_buffer):
    data = uart.read()
    if data:
        rx_buffer.extend(data)
    while True:
        if b"\n" not in rx_buffer:
            break
        line, _, remainder = bytes(rx_buffer).partition(b"\n")
        rx_buffer[:] = remainder
        parsed = parse_uart_line(line.decode("ascii", errors="ignore"))
        if parsed:
            apply_remote_event(parsed[0], parsed[1], keyboard, pressed)


# ------------------------------ Main Setup ------------------------------
keyboard = Keyboard(usb_hid.devices)
pressed_until = {}

uart = busio.UART(tx=None, rx=UART_RX_PIN, baudrate=UART_BAUD, timeout=0, receiver_buffer_size=128)
rx_buffer = bytearray()

def make_encoder(pin_a, pin_b, label):
    """Create an encoder, ensuring the two pins are sequential GPIO numbers."""

    def pin_id(pin):
        return getattr(pin, "id", getattr(pin, "number", None))

    a_id = pin_id(pin_a)
    b_id = pin_id(pin_b)
    first, second = pin_a, pin_b

    if a_id is not None and b_id is not None:
        if a_id > b_id:
            a_id, b_id = b_id, a_id
            first, second = pin_b, pin_a
        if b_id - a_id != 1:
            raise RuntimeError(f"{label} pins must be sequential GPIO pins (got {pin_a} and {pin_b})")

    try:
        return rotaryio.IncrementalEncoder(first, second)
    except RuntimeError as err:
        raise RuntimeError(f"Failed to init {label} encoder with pins {pin_a} and {pin_b}: {err}") from err


joystick_encoders = {name: make_encoder(pins[0], pins[1], f"joystick {name}") for name, pins in JOY_PINS.items()}
dual_encoders = {
    "x": make_encoder(*DUAL0_PINS["x"], label="dual-axis X"),
    "y": make_encoder(*DUAL0_PINS["y"], label="dual-axis Y"),
}
single_encoder = make_encoder(*SINGLE_PINS, label="single-axis")

last_positions = {}

# ------------------------------ Main Loop -------------------------------
while True:
    handle_local_joystick(joystick_encoders, last_positions, keyboard, pressed_until)
    handle_local_dualaxis(dual_encoders, last_positions, keyboard, pressed_until)
    handle_local_singleaxis(single_encoder, last_positions, keyboard, pressed_until)
    handle_uart_packets(uart, keyboard, pressed_until, rx_buffer)
    service_key_releases(keyboard, pressed_until)
