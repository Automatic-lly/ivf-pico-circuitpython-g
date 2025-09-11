# CircuitPython - Raspberry Pi Pico (RP2040)
# Two joysticks (4 axes) via ADS1115 -> HID Keyboard: WASD + Arrow keys
# + 8 Rotary Encoders -> custom key taps (CW/CCW) with real-time response

import time
import board
import busio
import usb_hid
import digitalio

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# =========================
# TUNABLE PARAMETERS (top)
# =========================
# Joystick thresholds (ADS -> 0..1023)
CENTER_MIN = 350
CENTER_MAX = 650

# Joystick performance / feel (tap mode)
LOOP_MS   = 1       # main loop cadence (lower = more responsive)
REPEAT_MS = 1       # interval between tap starts while active (lower = faster)
PULSE_MS  = 1       # key down time for joystick taps

ALTERNATE_DIAGONAL    = True
SIMULTANEOUS_DIAGONAL = False
HOLD_MODE = True     # True = hold while active; False = fast tap mode

# Encoder performance
ENCODER_BACKEND = "rotaryio"   # "rotaryio" (realtime) or "gpio" (fallback)
ENCODER_DETENT_STEPS = 4       # steps per physical detent (try 4 or 2)
ENCODER_MULTIPLIER   = 50      # taps per detent
ENCODER_PULSE_MS     = 4       # key down time per tap
ENCODER_BURST_SPACING_MS = 1   # spacing between taps inside a detent burst

# ADS1115 address (ADDR->GND = 0x48)
ADS_ADDR = 0x48

# =========================
# Hardware setup
# =========================
# I2C0 on Pico: SCL=GP1, SDA=GP0
i2c = busio.I2C(board.GP1, board.GP0)
ads = ADS.ADS1115(i2c, address=ADS_ADDR)
ads.gain = 1

# ADS channels: JOY1_Y=A0, JOY1_X=A1, JOY2_Y=A2, JOY2_X=A3
joy1_y = AnalogIn(ads, ADS.P0)
joy1_x = AnalogIn(ads, ADS.P1)
joy2_y = AnalogIn(ads, ADS.P2)
joy2_x = AnalogIn(ads, ADS.P3)

# HID keyboard
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
# Joystick engine (unchanged)
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
# Encoders (REAL-TIME)
# =========================
# Pins (CLK, DT) – avoid GP0/GP1 (I2C)
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

# (CW, CCW) per encoder
ENC_KEYS = [
    ('x', 'z'),   # 1
    ('n', 'm'),   # 2
    ('q', 'e'),   # 3
    ('o', 'p'),   # 4
    ('1', '0'),   # 5
    ('1', '0'),   # 6
    ('3', '2'),   # 7
    ('5', '4'),   # 8
]

# ---- Fast tap pipeline for encoders
enc_labels = set(sum(([cw, ccw] for cw, ccw in ENC_KEYS), []))
enc_is_down     = {lbl: False for lbl in enc_labels}
enc_release_due = {lbl: 0.0   for lbl in enc_labels}
enc_next_burst  = {lbl: 0.0   for lbl in enc_labels}  # spacing within a burst

def schedule_encoder_tap(label, now_ms):
    if now_ms < enc_next_burst[label]:
        return  # throttle inside burst
    if not enc_is_down[label]:
        press(label)
        enc_is_down[label]     = True
        enc_release_due[label] = now_ms + ENCODER_PULSE_MS
        enc_next_burst[label]  = now_ms + ENCODER_BURST_SPACING_MS
    else:
        # force a clean re-tap if somehow still down
        release(label)
        press(label)
        enc_release_due[label] = now_ms + ENCODER_PULSE_MS
        enc_next_burst[label]  = now_ms + ENCODER_BURST_SPACING_MS

def process_encoder_releases(now_ms):
    for lbl in enc_release_due:
        if enc_is_down[lbl] and now_ms >= enc_release_due[lbl]:
            release(lbl)
            enc_is_down[lbl] = False

# ---- Backend A: rotaryio (realtime)
_use_rotaryio = False
try:
    import rotaryio
    if ENCODER_BACKEND.lower() == "rotaryio":
        _use_rotaryio = True
except Exception:
    _use_rotaryio = False

if _use_rotaryio:
    # Create IncrementalEncoder objects
    enc_objs = []
    enc_last = []
    for (clk, dt) in ENC_PINS:
        enc = rotaryio.IncrementalEncoder(clk, dt)  # fast PIO/IRQ-backed
        enc_objs.append(enc)
        enc_last.append(enc.position)

else:
    # ---- Backend B: GPIO fallback (optimized Gray decoder)
    # 4-bit transition -> delta lookup
    _LUT = (
        0, -1, +1, 0,
       +1,  0,  0, -1,
       -1,  0,  0, +1,
        0, +1, -1, 0
    )

    class GPIOEnc:
        __slots__ = ("clk", "dt", "last_encoded", "accum")
        def __init__(self, clk_pin, dt_pin):
            self.clk = digitalio.DigitalInOut(clk_pin)
            self.clk.direction = digitalio.Direction.INPUT
            self.clk.pull = digitalio.Pull.UP
            self.dt  = digitalio.DigitalInOut(dt_pin)
            self.dt.direction = digitalio.Direction.INPUT
            self.dt.pull = digitalio.Pull.UP
            self.last_encoded = (int(self.clk.value) << 1) | int(self.dt.value)
            self.accum = 0  # accumulates +/- transitions

        def step_delta(self):
            msb = int(self.clk.value)
            lsb = int(self.dt.value)
            enc = (msb << 1) | lsb
            idx = ((self.last_encoded & 0x3) << 2) | (enc & 0x3)
            self.last_encoded = enc
            d = _LUT[idx]
            self.accum += d
            # Return full detents as +/- counts
            det = 0
            while self.accum >= ENCODER_DETENT_STEPS:
                self.accum -= ENCODER_DETENT_STEPS
                det += 1
            while self.accum <= -ENCODER_DETENT_STEPS:
                self.accum += ENCODER_DETENT_STEPS
                det -= 1
            return det

    gpio_encs = [GPIOEnc(clk, dt) for (clk, dt) in ENC_PINS]

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

        # ---- Encoders (REAL-TIME) ----
        now = time.monotonic() * 1000.0

        if _use_rotaryio:
            # Use .position deltas; convert to detents; fire bursts immediately
            for idx, enc in enumerate(enc_objs):
                pos = enc.position
                delta = pos - enc_last[idx]
                if delta:
                    enc_last[idx] = pos
                    # Convert raw edges to detents (rotaryio is typically 1 per edge)
                    # We aggregate so 'delta' edges -> +/-detents using ENCODER_DETENT_STEPS
                    if delta > 0:
                        det = delta // ENCODER_DETENT_STEPS
                        for _ in range(det * ENCODER_MULTIPLIER):
                            schedule_encoder_tap(ENC_KEYS[idx][0], now)
                    elif delta < 0:
                        det = (-delta) // ENCODER_DETENT_STEPS
                        for _ in range(det * ENCODER_MULTIPLIER):
                            schedule_encoder_tap(ENC_KEYS[idx][1], now)
        else:
            # GPIO fallback (optimized)
            for idx, ge in enumerate(gpio_encs):
                det = ge.step_delta()  # +/- detents
                if det > 0:
                    for _ in range(det * ENCODER_MULTIPLIER):
                        schedule_encoder_tap(ENC_KEYS[idx][0], now)
                elif det < 0:
                    for _ in range((-det) * ENCODER_MULTIPLIER):
                        schedule_encoder_tap(ENC_KEYS[idx][1], now)

        process_encoder_releases(now)

    except Exception as e:
        print("Error:", e)
        time.sleep(0.005)

    time.sleep(LOOP_MS / 1000.0)
