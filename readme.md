Pinout (Pico ⇄ Encoders & ADS1115)
Common

All encoder “C” (common) pins → GND

Use the encoder’s two signal pins as CLK and DT per the list below.
(Internal INPUT_PULLUP is enabled in code—so wiring is: signal → GPx, the other side of that switch → GND.)

Encoders (CLK, DT)

Enc1: CLK=GP2, DT=GP3 → keys: CW = x, CCW = z

Enc2: CLK=GP4, DT=GP5 → keys: CW = n, CCW = m

Enc3: CLK=GP6, DT=GP7 → keys: CW = q, CCW = e

Enc4: CLK=GP8, DT=GP9 → keys: CW = o, CCW = p

Enc5: CLK=GP10, DT=GP11 → keys: CW = 1, CCW = 0

Enc6: CLK=GP12, DT=GP13 → keys: CW = 1, CCW = 0

Enc7: CLK=GP14, DT=GP15 → keys: CW = 3, CCW = 2

Enc8: CLK=GP16, DT=GP17 → keys: CW = 5, CCW = 4

(These are chosen to avoid I²C pins GP0/GP1 and leave lots of contiguous pins for clean wiring.)

ADS1115 (I²C) + Joysticks

Pico GP0 (SDA) → ADS1115 SDA

Pico GP1 (SCL) → ADS1115 SCL

Pico 3V3 → ADS1115 VDD

Pico GND → ADS1115 GND

Joystick wipers → ADS A0/A1/A2/A3 respectively

Other joystick leads → 3V3 and GND

Notes

If your encoders detent differently (e.g., 2 transitions per detent), set ENCODER_DETENT_TRANSITIONS = 2.

To “speed up” encoders, increase ENCODER_MULTIPLIER (e.g., 2 or 3 taps per detent).

Joystick speed: lower REPEAT_MS and PULSE_MS. If you want even faster, you can try REPEAT_MS = 6, PULSE_MS = 4, and LOOP_MS = 1 (PC/host-dependent).

If you want the encoder key matrix changed or mirrored, just tweak ENC_KEYS—the rest auto-adjusts.