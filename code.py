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
# Config
# =========================
CENTER_MIN = 350   # widen deadzone to avoid jitter; tweak as needed
CENTER_MAX = 650
LOOP_MS = 10       # faster loop for smoother feel (was 30)

# Input mode:
HOLD_MODE = False   # True = hold keys while active; False = tap-repeat while active
REPEAT_MS = 20      # tap cadence while direction is active (lower = faster)
PULSE_MS  = 18      # how long each tap is held down (press -> small dwell -> release)
ALTERNATE_DIAGONAL = True   # alternate keys on diagonal: e.g., W,D,W,D,...
SIMULTANEOUS_DIAGONAL = False  # set True if you want to tap both keys at the same instant

ADS_ADDR = 0x48  # 0x48 if ADDR->GND

# I2C0 on Pico: SCL=GP1, SDA=GP0
i2c = busio.I2C(board.GP1, board.GP0)  # (SCL, SDA)

# ADS1115 setup
ads = ADS.ADS1115(i2c, address=ADS_ADDR)
ads.gain = 1  # +/- 4.096V (good for 3.3V joysticks)

# Channels: JOY1_Y=A0, JOY1_X=A1, JOY2_Y=A2, JOY2_X=A3
joy1_y = AnalogIn(ads, ADS.P0)
joy1_x = AnalogIn(ads, ADS.P1)
joy2_y = AnalogIn(ads, ADS.P2)
joy2_x = AnalogIn(ads, ADS.P3)

# HID keyboard
kbd = Keyboard(usb_hid.devices)

def to_0_1023(chan):
    # AnalogIn.value: 0..32767
    return chan.value // 32

# Key states (used only in HOLD_MODE)
joy1_state = {'w': False, 'a': False, 's': False, 'd': False}  # keep your mapping style
joy2_state = {'DOWN': False, 'UP': False, 'RIGHT': False, 'LEFT': False}

# Tap schedulers for both sticks (used when HOLD_MODE == False)
# We schedule taps per key so singles & diagonals can be independent
next_due1 = {'w': 0, 'a': 0, 's': 0, 'd': 0}
next_due2 = {'UP': 0, 'DOWN': 0, 'LEFT': 0, 'RIGHT': 0}
diag_toggle1 = False
diag_toggle2 = False

def press(kc):
    try:
        kbd.press(kc)
    except ValueError:
        pass  # already pressed

def release(kc):
    try:
        kbd.release(kc)
    except ValueError:
        pass  # already released

def tap_keycode(kc):
    # "Tap" a key quickly; small dwell helps some games register it
    press(kc)
    time.sleep(PULSE_MS / 1000.0)
    release(kc)

def keycode_from_label(label):
    # label is 'w','a','s','d' OR 'UP','DOWN','LEFT','RIGHT'
    if label in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
        return getattr(Keycode, f"{label}_ARROW")
    else:
        return getattr(Keycode, label.upper())

def handle_joysticks():
    global diag_toggle1, diag_toggle2

    j1y = to_0_1023(joy1_y)
    j1x = to_0_1023(joy1_x)
    j2y = to_0_1023(joy2_y)
    j2x = to_0_1023(joy2_x)

    # NOTE: your comment says "swapped mapping", but we'll respect the lines below exactly:
    # j1x < CENTER_MIN  => LEFT  => 'a'
    # j1x > CENTER_MAX  => RIGHT => 'd'
    want1 = {
        'w': (j1y < CENTER_MIN),
        's': (j1y > CENTER_MAX),
        'a': (j1x < CENTER_MIN),
        'd': (j1x > CENTER_MAX),
    }

    want2 = {
        'DOWN': (j2y < CENTER_MIN),
        'UP':   (j2y > CENTER_MAX),
        'RIGHT':(j2x < CENTER_MIN),
        'LEFT': (j2x > CENTER_MAX),
    }

    if HOLD_MODE:
        # --- HOLD MODE (unchanged behavior): hold keys while active ---
        for k in ('w','a','s','d'):
            cur, nxt = joy1_state[k], want1[k]
            if nxt and not cur:
                press(keycode_from_label(k))
                joy1_state[k] = True
            elif cur and not nxt:
                release(keycode_from_label(k))
                joy1_state[k] = False

        for k in ('DOWN','UP','RIGHT','LEFT'):
            cur, nxt = joy2_state[k], want2[k]
            if nxt and not cur:
                press(keycode_from_label(k))
                joy2_state[k] = True
            elif cur and not nxt:
                release(keycode_from_label(k))
                joy2_state[k] = False
        return

    # --- TAP-REPEAT MODE (fast multi-click, diagonal alternation) ---
    now = time.monotonic() * 1000.0  # ms

    # --- Joystick 1 (WASD) ---
    active1 = [k for k in ('w','a','s','d') if want1[k]]

    if len(active1) == 2 and ALTERNATE_DIAGONAL and not SIMULTANEOUS_DIAGONAL:
        # diagonal: alternate the two keys for wdwdwd... or awawaw...
        k = active1[0] if diag_toggle1 else active1[1]
        if now >= next_due1[k]:
            tap_keycode(keycode_from_label(k))
            next_due1[k] = now + REPEAT_MS
        # keep the partner in sync so it fires on the next cycle
        other = active1[1] if diag_toggle1 else active1[0]
        if next_due1[other] < now:
            next_due1[other] = now + REPEAT_MS // 2
        diag_toggle1 = not diag_toggle1
    elif len(active1) == 2 and SIMULTANEOUS_DIAGONAL:
        # diagonal: tap both at (almost) the same moment
        k1, k2 = active1
        if now >= min(next_due1[k1], next_due1[k2]):
            tap_keycode(keycode_from_label(k1))
            tap_keycode(keycode_from_label(k2))
            next_due1[k1] = now + REPEAT_MS
            next_due1[k2] = now + REPEAT_MS
    else:
        # singles or 3/4 keys: each key repeats on its own schedule
        for k in active1:
            if now >= next_due1[k]:
                tap_keycode(keycode_from_label(k))
                next_due1[k] = now + REPEAT_MS
        # reset timers for inactive keys so they fire immediately when re-entering
        for k in ('w','a','s','d'):
            if k not in active1:
                next_due1[k] = 0

    # --- Joystick 2 (Arrows) ---
    active2 = [k for k in ('DOWN','UP','RIGHT','LEFT') if want2[k]]

    if len(active2) == 2 and ALTERNATE_DIAGONAL and not SIMULTANEOUS_DIAGONAL:
        k = active2[0] if diag_toggle2 else active2[1]
        if now >= next_due2[k]:
            tap_keycode(keycode_from_label(k))
            next_due2[k] = now + REPEAT_MS
        other = active2[1] if diag_toggle2 else active2[0]
        if next_due2[other] < now:
            next_due2[other] = now + REPEAT_MS // 2
        diag_toggle2 = not diag_toggle2
    elif len(active2) == 2 and SIMULTANEOUS_DIAGONAL:
        k1, k2 = active2
        if now >= min(next_due2[k1], next_due2[k2]):
            tap_keycode(keycode_from_label(k1))
            tap_keycode(keycode_from_label(k2))
            next_due2[k1] = now + REPEAT_MS
            next_due2[k2] = now + REPEAT_MS
    else:
        for k in active2:
            if now >= next_due2[k]:
                tap_keycode(keycode_from_label(k))
                next_due2[k] = now + REPEAT_MS
        for k in ('DOWN','UP','RIGHT','LEFT'):
            if k not in active2:
                next_due2[k] = 0

print("HELLO CIRCUITPY READY (ADS1115 HID)")

while True:
    try:
        handle_joysticks()
    except Exception as e:
        print("Error:", e)
        time.sleep(0.05)
    time.sleep(LOOP_MS / 1000)
