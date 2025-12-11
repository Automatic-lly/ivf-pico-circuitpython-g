"""
Slave controller for dual-board encoder + joystick HID system.
Sends encoder activity over UART to the master Pico.
"""
import time
import board
import busio
import rotaryio

from slave_keymap import dual_packet, joystick_packet, single_packet

UART_BAUD = 115200
UART_TX_PIN = board.GP0

JOY_PINS = {
    "0": (board.GP2, board.GP3),  # X-axis
    "1": (board.GP4, board.GP5),  # Y-axis
    "2": (board.GP6, board.GP7),  # Twist
}

DUAL_PINS = {
    0: {
        "0": (board.GP8, board.GP9),
        "1": (board.GP10, board.GP11),
    },
    1: {
        "0": (board.GP12, board.GP13),
        "1": (board.GP14, board.GP15),
    },
}

SINGLE_PINS = (board.GP16, board.GP17)


def now_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def process_encoder(enc: rotaryio.IncrementalEncoder, last_positions: dict, name: str, callback) -> None:
    pos = enc.position
    last = last_positions.get(name, 0)
    delta = pos - last
    if delta == 0:
        return
    direction = "+" if delta > 0 else "-"
    for _ in range(abs(delta)):
        callback(direction)
    last_positions[name] = pos


def make_encoder(pin_a, pin_b, label):
    """Create an encoder, ensuring its pins are sequential GPIO numbers."""

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


def main():
    uart = busio.UART(tx=UART_TX_PIN, rx=None, baudrate=UART_BAUD, timeout=0)

    joystick = {axis: make_encoder(pins[0], pins[1], f"joystick {axis}") for axis, pins in JOY_PINS.items()}
    dual_encoders = {
        idx: {axis: make_encoder(*pins, label=f"dual {idx} axis {axis}") for axis, pins in axis_map.items()}
        for idx, axis_map in DUAL_PINS.items()
    }
    single = make_encoder(*SINGLE_PINS, label="single-axis")

    last_positions = {}

    def send_packet(packet: str):
        uart.write((packet + "\n").encode("ascii"))

    while True:
        # Joystick encoders
        for axis, encoder in joystick.items():
            def make_cb(axis_code):
                return lambda direction: send_packet(joystick_packet(axis_code, direction))

            process_encoder(encoder, last_positions, f"joy_{axis}", make_cb(axis))

        # Dual-axis encoders
        for idx, enc_map in dual_encoders.items():
            for axis, encoder in enc_map.items():
                def make_cb(e_idx, axis_code):
                    return lambda direction: send_packet(dual_packet(e_idx, axis_code, direction))

                process_encoder(encoder, last_positions, f"dual{idx}_{axis}", make_cb(idx, axis))

        # Single-axis encoder
        process_encoder(single, last_positions, "single", lambda direction: send_packet(single_packet(direction)))

        # Optional tiny yield to keep loop responsive without blocking
        _ = now_ms()


main()
