# CircuitPython - Raspberry Pi Pico (RP2040)
# Two joysticks (4 axes) via ADS1115 -> HID Keyboard: WASD + Arrow keys
# + 8 Rotary Encoders -> realtime taps (1 edge = 1 key)

import time
import board
import busio
import usb_hid
import digitalio
import rotaryio

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# =========================
# TUNABLE PARAMETERS
# =========================
CENTER_MIN = 350
CENTER_MAX = 650

# Joystick performance / feel
LOOP_MS   = 1
REPEAT_MS = 1
PULSE_MS  = 1

ALTERNATE_DIAGONAL    = True
SIMULTANEOUS_DIAGONAL = False
HOLD_MODE = False   # True = hold, False = fast tap

# Encoder performance
ENCODER_PULSE_MS     = 4   # key down time per tap
ENCODER_BURST_SPACING_MS = 1  # spacing between taps in a burst

# ADS1115 address
ADS_ADDR = 0x48

# =========================
# Hardware setup
# =========================
i2c = busio.I2C(board.GP1, board.GP0)  # SCL=GP1, SDA=GP0
ads = ADS.ADS1115(i2c, address=ADS_ADDR)
ads.gain = 1

joy1_y = AnalogIn(ads, ADS.P0)
joy1_x = AnalogIn(ads, ADS.P1)
joy2_y = AnalogIn(ads, ADS.P2)
joy2_x = AnalogIn(ads, ADS.P3)

kbd = Keyboard(usb_hid.devices)

# =========================
# Helpers & key mapping
# =========================
DIGIT_MAP = {
    '0': Keycode.ZERO, '1': Keycode.ONE, '2': Keycode.TWO, '3': Keycode.THREE,
    '4': Keycode.FOUR, '5': Keycode.FIVE, '6': Keycode.SIX, '7': Keycode.SEVEN,
    '8': Keycode.EIGHT, '9': Keycode.NINE
}

def keycode_from_label(label):
    if label in ('UP', 'DOWN', 'LEFT', 'RIGHT'):
        return getattr(Keycode, f"{label}_ARROW")
    if label in DIGIT_MAP:
        return DIGIT_MAP[label]
    return getattr(Keycode, label.upper())

def to_0_1023(chan):
    return chan.value // 32

def press(label):
    try: kbd.press(keycode_from_label(label))
    except ValueError: pass

def release(label):
    try: kbd.release(keycode_from_label(label))
    except ValueError: pass

# =========================
# Joystick engine
# =========================
labels1 = ('w', 'a', 's', 'd')
labels2 = ('DOWN', 'UP', 'RIGHT', 'LEFT')

joy1_hold = {k: False for k in labels1}
joy2_hold = {k: False for k in labels2}

is_down1     = {k: False for k in labels1}
release_due1 = {k: 0.0   for k in labels1}
next_due1    = {k: 0.0   for k in labels1}
diag_toggle1 = False

is_down2     = {k: False for k in labels2}
release_due2 = {k: 0.0   for k in labels2}
next_due2    = {k: 0.0   for k in labels2}
diag_toggle2 = False

def handle_hold(joy_state, want, order):
    for k in order:
        cur, nxt = joy_state[k], want[k]
        if nxt and not cur:
            press(k); joy_state[k] = True
        elif cur and not nxt:
            release(k); joy_state[k] = False

def schedule_tap_set(active, now_ms, is_down, next_due, release_due, diag_toggle):
    if len(active) == 2 and ALTERNATE_DIAGONAL and not SIMULTANEOUS_DIAGONAL:
        k = active[0] if diag_toggle else active[1]
        if now_ms >= next_due[k] and not is_down[k]:
            press(k); is_down[k] = True
            release_due[k] = now_ms + PULSE_MS
            next_due[k]    = now_ms + REPEAT_MS
        other = active[1] if diag_toggle else active[0]
        if next_due[other] < now_ms:
            next_due[other] = now_ms + REPEAT_MS * 0.5
        return not diag_toggle

    if len(active) == 2 and SIMULTANEOUS_DIAGONAL:
        k1, k2 = active
        if now_ms >= min(next_due[k1], next_due[k2]):
            if not is_down[k1]:
                press(k1); is_down[k1] = True; release_due[k1] = now_ms + PULSE_MS
            if not is_down[k2]:
                press(k2); is_down[k2] = True; release_due[k2] = now_ms + PULSE_MS
            next_due[k1] = now_ms + REPEAT_MS
            next_due[k2] = now_ms + REPEAT_MS
        return diag_toggle

    for k in active:
        if now_ms >= next_due[k] and not is_down[k]:
            press(k); is_down[k] = True
            release_due[k] = now_ms + PULSE_MS
            next_due[k]    = now_ms + REPEAT_MS

    for k in next_due:
        if k not in active:
            next_due[k] = 0.0
    return diag_toggle

def process_releases(now_ms, is_down, release_due):
    for k in release_due:
        if is_down[k] and now_ms >= release_due[k]:
            release(k); is_down[k] = False

# =========================
# Encoders (Realtime Edge→Tap)
# =========================
ENC_PINS = [
    (board.GP2,  board.GP3),   # Enc1
    (board.GP4,  board.GP5),   # Enc2
    (board.GP6,  board.GP7),   # Enc3
    (board.GP8,  board.GP9),   # Enc4
    (board.GP10, board.GP11),  # Enc5
    (board.GP12, board.GP13),  # Enc6
    (board.GP14, board.GP15),  # Enc7
    (board.GP16, board.GP17),  # Enc8
]

ENC_KEYS = [
    ('x', 'z'),
    ('n', 'm'),
    ('q', 'e'),
    ('o', 'p'),
    ('1', '0'),
    ('1', '0'),
    ('3', '2'),
    ('5', '4'),
]

# Create rotaryio encoders
enc_objs = []
enc_last = []
for (clk, dt) in ENC_PINS:
    enc = rotaryio.IncrementalEncoder(clk, dt)
    enc_objs.append(enc)
    enc_last.append(enc.position)

# Fast tap scheduler for encoders
enc_labels = set(sum(([cw, ccw] for cw, ccw in ENC_KEYS), []))
enc_is_down     = {lbl: False for lbl in enc_labels}
enc_release_due = {lbl: 0.0   for lbl in enc_labels}
enc_next_burst  = {lbl: 0.0   for lbl in enc_labels}

def schedule_encoder_tap(label, now_ms):
    if now_ms < enc_next_burst[label]:
        return
    if not enc_is_down[label]:
        press(label)
        enc_is_down[label]     = True
        enc_release_due[label] = now_ms + ENCODER_PULSE_MS
        enc_next_burst[label]  = now_ms + ENCODER_BURST_SPACING_MS
    else:
        release(label)
        press(label)
        enc_release_due[label] = now_ms + ENCODER_PULSE_MS
        enc_next_burst[label]  = now_ms + ENCODER_BURST_SPACING_MS

def process_encoder_releases(now_ms):
    for lbl in enc_release_due:
        if enc_is_down[lbl] and now_ms >= enc_release_due[lbl]:
            release(lbl)
            enc_is_down[lbl] = False

def handle_encoders(now):
    for idx, enc in enumerate(enc_objs):
        pos = enc.position
        delta = pos - enc_last[idx]
        if delta > 0:
            for _ in range(delta):
                schedule_encoder_tap(ENC_KEYS[idx][0], now)
        elif delta < 0:
            for _ in range(-delta):
                schedule_encoder_tap(ENC_KEYS[idx][1], now)
        enc_last[idx] = pos

# =========================
# Main loop
# =========================
print("HELLO CIRCUITPY READY (ADS1115 HID + REALTIME ENCODERS)")

while True:
    try:
        # ---- Joysticks ----
        j1y = to_0_1023(joy1_y); j1x = to_0_1023(joy1_x)
        j2y = to_0_1023(joy2_y); j2x = to_0_1023(joy2_x)

        want1 = {
            'w': (j1y < CENTER_MIN),
            's': (j1y > CENTER_MAX),
            'a': (j1x < CENTER_MIN),
            'd': (j1x > CENTER_MAX),
        }
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
            now = time.monotonic() * 1000.0
            active1 = [k for k in ('w','a','s','d') if want1[k]]
            active2 = [k for k in ('DOWN','UP','RIGHT','LEFT') if want2[k]]
            diag_toggle1 = schedule_tap_set(active1, now, is_down1, next_due1, release_due1, diag_toggle1)
            diag_toggle2 = schedule_tap_set(active2, now, is_down2, next_due2, release_due2, diag_toggle2)
            process_releases(now, is_down1, release_due1)
            process_releases(now, is_down2, release_due2)

        # ---- Encoders ----
        now = time.monotonic() * 1000.0
        handle_encoders(now)
        process_encoder_releases(now)

    except Exception as e:
        print("Error:", e)
        time.sleep(0.005)

    time.sleep(LOOP_MS / 1000.0)
