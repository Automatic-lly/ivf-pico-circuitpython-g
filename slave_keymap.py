"""Packet format helpers for the slave controller."""

# Axis codes used in UART packets
JOYSTICK_AXIS_CODES = ("0", "1", "2")  # x, y, twist
DUAL_AXIS_CODES = ("0", "1")  # x, y


def joystick_packet(axis_code: str, direction: str) -> str:
    return f"J{axis_code}{direction}"


def dual_packet(idx: int, axis_code: str, direction: str) -> str:
    return f"D{idx} {axis_code} {direction}"


def single_packet(direction: str) -> str:
    return f"S{direction}"
