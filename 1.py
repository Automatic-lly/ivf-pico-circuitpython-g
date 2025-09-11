from machine import Pin
from time import sleep

# Built-in LED is connected to GPIO 25
led = Pin(25, Pin.OUT)

while True:
    led.toggle()      # Toggle the LED state
    sleep(1)          # Wait for 1 second
