# CircuitPython - Raspberry Pi Pico (RP2040)
# Two joysticks (4 axes) via ADS1115 -> HID Keyboard: WASD + Arrow keys
# + 8 Rotary Encoders -> realtime taps (1 edge = 1 key)

import time
import board
import busio
import usb_hid
import rotaryio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# =========================
# TUNABLE PARAMETERS
# =========================
CENTER_MIN = 350
CENTER_MAX = 650

LOOP_MS = 1  # main loop cadence (ms)

# Joystick fast-tap parameters
PULSE_MS = 1  # how long key stays pressed (ms)

# Encoder fast tap
ENCODER_PULSE_MS = 4
ENCODER_BURST_SPACING_MS = 1

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
    try:
        kbd.press(keycode_from_label(label))
    except ValueError:
        pass

def release(label):
    try:
        kbd.release(keycode_from_label(label))
    except ValueError:
        pass

# =========================
# Joystick engine (fast tap)
# =========================
labels1 = ('w', 'a', 's', 'd')
labels2 = ('DOWN', 'UP', 'RIGHT', 'LEFT')

release_due = {}

def handle_joystick_fasttap(want, labels, now_ms):
    for k in labels:
        if want[k]:
            press(k)
            release_due[k] = now_ms + PULSE_MS
        if k in release_due and now_ms >= release_due[k]:
            release(k)
            release_due[k] = now_ms + 999999  # disable until next tap

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
    ('m', 'n'),
    ('z', 'x'),
    ('e', 'q'),
    ('p', 'o'),
    ('1', '0'),
    ('0', '1'),
    ('4', '5'),
    ('2', '3'),
]

enc_objs = []
enc_last = []
for (clk, dt) in ENC_PINS:
    enc = rotaryio.IncrementalEncoder(clk, dt)
    enc_objs.append(enc)
    enc_last.append(enc.position)

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
print("HELLO CIRCUITPY READY (ADS1115 HID + REALTIME ENCODERS + FASTTAP JOYSTICKS)")

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

        now = time.monotonic() * 1000.0
        handle_joystick_fasttap(want1, labels1, now)
        handle_joystick_fasttap(want2, labels2, now)

        # ---- Encoders ----
        handle_encoders(now)
        process_encoder_releases(now)

    except Exception as e:
        print("Error:", e)
        time.sleep(0.005)

    time.sleep(LOOP_MS / 1000.0)
