# CircuitPython - Raspberry Pi Pico (RP2040)
# Two joysticks (4 axes) via ADS1115 -> HID Keyboard: WASD + Arrow keys

import time
import board
import busio
import usb_hid

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# NOTE: import the MODULE as ADS (so we can use ADS.P0/P1/P2/P3)
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# =========================
# TUNABLE PARAMETERS (top)
# =========================
# Deadzone (ADS -> 0..1023)
CENTER_MIN = 350
CENTER_MAX = 650

# Performance / feel
LOOP_MS   = 1     # main loop cadence (lower = more responsive CPU permitting)
REPEAT_MS = 1   # interval between tap starts while direction is active (lower = faster)
PULSE_MS  = 1      # how long each tap stays held before release (lower = crisper)

# Diagonal tap style (tap mode only)
ALTERNATE_DIAGONAL    = True   # wdwdwd… (alternating) for diagonals
SIMULTANEOUS_DIAGONAL = False  # tap both at once when diagonal; leave False if ALTERNATE is True

# Mode: hold vs tap-repeat
HOLD_MODE = True   # False = fast tap mode, True = hold-while-active

# ADS1115 I2C address (ADDR->GND = 0x48)
ADS_ADDR = 0x48

# =========================
# Hardware setup
# =========================
# I2C0 on Pico: SCL=GP1, SDA=GP0
i2c = busio.I2C(board.GP1, board.GP0)  # (SCL, SDA)

# ADS1115 setup
ads = ADS.ADS1115(i2c, address=ADS_ADDR)
ads.gain = 1  # +/- 4.096V (good for 3.3V sticks)

# Channels: JOY1_Y=A0, JOY1_X=A1, JOY2_Y=A2, JOY2_X=A3
joy1_y = AnalogIn(ads, ADS.P0)
joy1_x = AnalogIn(ads, ADS.P1)
joy2_y = AnalogIn(ads, ADS.P2)
joy2_x = AnalogIn(ads, ADS.P3)

# HID keyboard
kbd = Keyboard(usb_hid.devices)

# =========================
# Helpers & state
# =========================
def to_0_1023(chan):
    # AnalogIn.value: 0..32767
    return chan.value // 32

# For HOLD mode
joy1_hold = {'w': False, 'a': False, 's': False, 'd': False}
joy2_hold = {'DOWN': False, 'UP': False, 'RIGHT': False, 'LEFT': False}

# For TAP mode (non-blocking scheduler)
labels1 = ('w', 'a', 's', 'd')
labels2 = ('DOWN', 'UP', 'RIGHT', 'LEFT')

# Press/release states for taps
is_down1     = {k: False for k in labels1}
release_due1 = {k: 0.0   for k in labels1}
next_due1    = {k: 0.0   for k in labels1}
diag_toggle1 = False

is_down2     = {k: False for k in labels2}
release_due2 = {k: 0.0   for k in labels2}
next_due2    = {k: 0.0   for k in labels2}
diag_toggle2 = False

def keycode_from_label(label):
    if label in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
        return getattr(Keycode, f"{label}_ARROW")
    return getattr(Keycode, label.upper())

def press(label):
    try:
        kbd.press(keycode_from_label(label))
    except ValueError:
        pass

def release(label):
    try:
        kbd.release(keycode_from_label(label))
    except ValueError:
        pass

def handle_hold(joy_state, want, order):
    for k in order:
        cur, nxt = joy_state[k], want[k]
        if nxt and not cur:
            press(k); joy_state[k] = True
        elif cur and not nxt:
            release(k); joy_state[k] = False

def schedule_tap_set(active, now_ms, is_down, next_due, release_due, diag_toggle):
    """
    Schedules taps (press now, release later) WITHOUT sleeping.
    Returns updated diag_toggle.
    """
    # handle diagonals
    if len(active) == 2 and ALTERNATE_DIAGONAL and not SIMULTANEOUS_DIAGONAL:
        k = active[0] if diag_toggle else active[1]
        if now_ms >= next_due[k] and not is_down[k]:
            press(k)
            is_down[k]     = True
            release_due[k] = now_ms + PULSE_MS
            next_due[k]    = now_ms + REPEAT_MS
        # nudge partner so it fires next half-step
        other = active[1] if diag_toggle else active[0]
        if next_due[other] < now_ms:
            next_due[other] = now_ms + REPEAT_MS * 0.5
        return not diag_toggle

    if len(active) == 2 and SIMULTANEOUS_DIAGONAL:
        k1, k2 = active
        if now_ms >= min(next_due[k1], next_due[k2]):
            # press both (if not already down)
            if not is_down[k1]:
                press(k1); is_down[k1] = True; release_due[k1] = now_ms + PULSE_MS
            if not is_down[k2]:
                press(k2); is_down[k2] = True; release_due[k2] = now_ms + PULSE_MS
            next_due[k1] = now_ms + REPEAT_MS
            next_due[k2] = now_ms + REPEAT_MS
        return diag_toggle

    # singles or 3/4 keys: each on its own cadence
    for k in active:
        if now_ms >= next_due[k] and not is_down[k]:
            press(k)
            is_down[k]     = True
            release_due[k] = now_ms + PULSE_MS
            next_due[k]    = now_ms + REPEAT_MS

    # reset timers for inactive so next entry fires immediately
    for k in next_due:
        if k not in active:
            next_due[k] = 0.0
    return diag_toggle

def process_releases(now_ms, is_down, release_due):
    # release any keys whose hold time expired
    for k in release_due:
        if is_down[k] and now_ms >= release_due[k]:
            release(k)
            is_down[k] = False

print("HELLO CIRCUITPY READY (ADS1115 HID FAST TAP)")

# =========================
# Main loop
# =========================
while True:
    try:
        j1y = to_0_1023(joy1_y)
        j1x = to_0_1023(joy1_x)
        j2y = to_0_1023(joy2_y)
        j2x = to_0_1023(joy2_x)

        # WASD mapping (left='a', right='d')
        want1 = {
            'w': (j1y < CENTER_MIN),
            's': (j1y > CENTER_MAX),
            'a': (j1x < CENTER_MIN),
            'd': (j1x > CENTER_MAX),
        }

        # Arrow mapping (keep your orientation)
        want2 = {
            'DOWN':  (j2y < CENTER_MIN),
            'UP':    (j2y > CENTER_MAX),
            'RIGHT': (j2x < CENTER_MIN),
            'LEFT':  (j2x > CENTER_MAX),
        }

        if HOLD_MODE:
            handle_hold(joy1_hold, want1, ('w','a','s','d'))
            handle_hold(joy2_hold, want2, ('DOWN','UP','RIGHT','LEFT'))
        else:
            now = time.monotonic() * 1000.0  # ms

            # Build active lists (which directions are currently "on")
            active1 = [k for k in ('w','a','s','d')            if want1[k]]
            active2 = [k for k in ('DOWN','UP','RIGHT','LEFT') if want2[k]]

            # Schedule taps (no blocking)
            diag_toggle1 = schedule_tap_set(active1, now, is_down1, next_due1, release_due1, diag_toggle1)
            diag_toggle2 = schedule_tap_set(active2, now, is_down2, next_due2, release_due2, diag_toggle2)

            # Release any taps that completed their pulse time
            process_releases(now, is_down1, release_due1)
            process_releases(now, is_down2, release_due2)

    except Exception as e:
        print("Error:", e)
        time.sleep(0.02)

    time.sleep(LOOP_MS / 1000.0)
