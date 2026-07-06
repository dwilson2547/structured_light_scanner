# Trigger/strobe firmware for Raspberry Pi Pico (MicroPython).
#
# Wiring (change PIN_* to match the build):
#   GP2  -> FSIN/trigger input of BOTH cameras (fanned out)
#   GP3  -> laser A MOSFET gate
#   GP4  -> laser B MOSFET gate
#   GP5  -> grip button to GND (internal pull-up), toggles START/STOP
#
# Serial protocol (USB CDC, 115200, newline-terminated — see sls/capture/trigger.py):
#   START <fps> <AB0|A0|ON|OFF>
#   STOP
#   LASER <A|B> <0|1>
#   PING
#
# Timing per frame: lasers are set for the *next* frame, a settle delay passes,
# then FSIN pulses. Trigger polarity/width may need adjusting per the Arducam
# datasheet for your module (default: 100 us active-high pulse).

import sys
import time

from machine import Pin, Timer

PIN_FSIN = 2
PIN_LASER_A = 3
PIN_LASER_B = 4
PIN_BUTTON = 5

FSIN_PULSE_US = 100
LASER_SETTLE_US = 200

PATTERNS = {
    "AB0": ((1, 0), (0, 1), (0, 0)),
    "A0": ((1, 0), (0, 0)),
    "ON": ((1, 1),),
    "OFF": ((0, 0),),
}

fsin = Pin(PIN_FSIN, Pin.OUT, value=0)
laser_a = Pin(PIN_LASER_A, Pin.OUT, value=0)
laser_b = Pin(PIN_LASER_B, Pin.OUT, value=0)
button = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)

timer = Timer()
running = False
pattern = PATTERNS["OFF"]
frame = 0
last_fps = 30


def _tick(_t):
    global frame
    a, b = pattern[frame % len(pattern)]
    laser_a.value(a)
    laser_b.value(b)
    time.sleep_us(LASER_SETTLE_US)
    fsin.value(1)
    time.sleep_us(FSIN_PULSE_US)
    fsin.value(0)
    frame += 1


def start(fps, pat_name):
    global running, pattern, frame, last_fps
    stop()
    pattern = PATTERNS[pat_name]
    frame = 0
    last_fps = fps
    timer.init(freq=fps, mode=Timer.PERIODIC, callback=_tick)
    running = True


def stop():
    global running
    timer.deinit()
    laser_a.value(0)
    laser_b.value(0)
    running = False


def handle(line):
    parts = line.strip().split()
    if not parts:
        return None
    cmd = parts[0].upper()
    if cmd == "PING":
        return "ok pong"
    if cmd == "STOP":
        stop()
        return "ok stopped"
    if cmd == "START" and len(parts) == 3:
        try:
            fps = int(parts[1])
        except ValueError:
            return "err bad fps"
        pat = parts[2].upper()
        if pat not in PATTERNS or not (1 <= fps <= 120):
            return "err bad args"
        start(fps, pat)
        return "ok started %d %s" % (fps, pat)
    if cmd == "LASER" and len(parts) == 3:
        if running:
            return "err running"
        pin = {"A": laser_a, "B": laser_b}.get(parts[1].upper())
        if pin is None or parts[2] not in ("0", "1"):
            return "err bad args"
        pin.value(int(parts[2]))
        return "ok"
    return "err unknown"


def main():
    btn_prev = 1
    buf = ""
    poll = sys.stdin
    while True:
        # button edge -> toggle scan at last-used settings
        btn = button.value()
        if btn_prev == 1 and btn == 0:
            if running:
                stop()
            else:
                start(last_fps, "AB0")
            time.sleep_ms(200)  # debounce
        btn_prev = btn

        ch = poll.read(1) if hasattr(poll, "any") and poll.any() else None
        if ch:
            buf += ch
            if buf.endswith("\n"):
                resp = handle(buf)
                buf = ""
                if resp:
                    print(resp)
        else:
            time.sleep_ms(2)


main()
