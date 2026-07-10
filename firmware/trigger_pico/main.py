# Trigger/strobe firmware for Raspberry Pi Pico (MicroPython).
#
# Wiring (change PIN_* to match the build):
#   GP2  -> FSIN/trigger input of BOTH cameras (fanned out)
#   GP3  -> laser A MOSFET gate
#   GP4  -> laser B MOSFET gate
#   GP5  -> grip button to GND (internal pull-up), toggles START/STOP
#   GP6  <- left camera STROBE output  (exposure-active, for SYNC check)
#   GP7  <- right camera STROBE output
#
# Serial protocol (USB CDC, 115200, newline-terminated — see sls/capture/trigger.py):
#   START <fps> <AB0|A0|ON|OFF>
#   STOP
#   LASER <A|B> <0|1>
#   SYNC [n]
#   PING
#
# Timing per frame: lasers are set for the *next* frame, a settle delay passes,
# then FSIN pulses. Trigger polarity/width may need adjusting per the Arducam
# datasheet for your module (default: 100 us active-high pulse).

import array
import select
import sys
import time

import micropython
from machine import Pin, Timer

PIN_FSIN = 2
PIN_LASER_A = 3
PIN_LASER_B = 4
PIN_BUTTON = 5
PIN_STROBE_L = 6
PIN_STROBE_R = 7

FSIN_PULSE_US = 100
LASER_SETTLE_US = 200

# Low-side N-channel drivers: gate high = laser ON (see README circuit spec).
# Set True if the build ever moves to high-side P-channel (gate low = ON).
LASER_ACTIVE_LOW = False
_LASER_OFF = 1 if LASER_ACTIVE_LOW else 0

PATTERNS = {
    "AB0": ((1, 0), (0, 1), (0, 0)),
    "A0": ((1, 0), (0, 0)),
    "ON": ((1, 1),),
    "OFF": ((0, 0),),
}

fsin = Pin(PIN_FSIN, Pin.OUT, value=0)
laser_a = Pin(PIN_LASER_A, Pin.OUT, value=_LASER_OFF)
laser_b = Pin(PIN_LASER_B, Pin.OUT, value=_LASER_OFF)


def _laser(pin, on):
    pin.value(on ^ 1 if LASER_ACTIVE_LOW else on)
button = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)
strobe_l = Pin(PIN_STROBE_L, Pin.IN, Pin.PULL_DOWN)
strobe_r = Pin(PIN_STROBE_R, Pin.IN, Pin.PULL_DOWN)

timer = Timer()
running = False
pattern = PATTERNS["OFF"]
frame = 0
last_fps = 30


def _tick(_t):
    global frame
    a, b = pattern[frame % len(pattern)]
    _laser(laser_a, a)
    _laser(laser_b, b)
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
    _laser(laser_a, 0)
    _laser(laser_b, 0)
    running = False


# --- SYNC: verify both cameras expose simultaneously off one FSIN pulse ---
#
# Each camera's STROBE output is high while its sensor is exposing. After one
# FSIN pulse we busy-poll the SIO GPIO_IN register (one atomic 32-bit read
# samples BOTH strobe pins, so there is no channel-ordering bias) and record
# the loop-iteration index of each strobe's rise and fall. Iterations are
# calibrated against ticks_us, giving sub-microsecond effective resolution —
# a MicroPython pin IRQ would add tens of us of jitter, which is why this
# polls instead.


@micropython.viper
def _pulse_watch(fsin_mask: int, ml: int, mr: int, pulse_n: int,
                 timeout: int, out: ptr32) -> int:
    sio = ptr32(0xD0000000)  # RP2040 SIO: [1]=GPIO_IN [5]=OUT_SET [6]=OUT_CLR
    both = ml | mr
    idle = sio[1] & both     # polarity-agnostic: an edge is a change from idle
    rl = -1
    rr = -1
    fl = -1
    fr = -1
    sio[5] = fsin_mask
    i = 0
    while i < timeout:
        if i == pulse_n:
            sio[6] = fsin_mask
        v = (sio[1] & both) ^ idle
        if v & ml:
            if rl < 0:
                rl = i
        elif rl >= 0 and fl < 0:
            fl = i
        if v & mr:
            if rr < 0:
                rr = i
        elif rr >= 0 and fr < 0:
            fr = i
        if fl >= 0 and fr >= 0:
            break
        i += 1
    sio[6] = fsin_mask  # ensure FSIN low even on timeout
    out[0] = rl
    out[1] = rr
    out[2] = fl
    out[3] = fr
    return i


def _iters_per_ms():
    out = array.array("i", [0, 0, 0, 0])
    t0 = time.ticks_us()
    _pulse_watch(0, 0, 0, -1, 100000, out)  # no pins: runs exactly 100k iters
    dt = time.ticks_diff(time.ticks_us(), t0)
    return max(1, 100000 * 1000 // dt)


def sync_check(n):
    stop()
    out = array.array("i", [0, 0, 0, 0])
    ipms = _iters_per_ms()
    ns_per_iter = 1000000 // ipms
    pulse_n = max(1, ipms * FSIN_PULSE_US // 1000)
    timeout = ipms * 50  # 50 ms >> trigger latency + exposure
    fsin_mask = 1 << PIN_FSIN
    ml, mr = 1 << PIN_STROBE_L, 1 << PIN_STROBE_R
    miss_l = miss_r = 0
    dts, lat_l, lat_r, wid_l, wid_r = [], [], [], [], []
    for _ in range(n):
        _pulse_watch(fsin_mask, ml, mr, pulse_n, timeout, out)
        rl, rr, fl, fr = out
        if rl < 0:
            miss_l += 1
        if rr < 0:
            miss_r += 1
        if rl >= 0 and rr >= 0:
            dts.append((rl - rr) * ns_per_iter)
            lat_l.append(rl * ns_per_iter)
            lat_r.append(rr * ns_per_iter)
            if fl >= 0:
                wid_l.append((fl - rl) * ns_per_iter)
            if fr >= 0:
                wid_r.append((fr - rr) * ns_per_iter)
        time.sleep_ms(30)  # let readout finish before the next trigger
    if not dts:
        return "err sync no strobes (miss L=%d R=%d of %d) — check wiring/trigger mode" % (
            miss_l, miss_r, n)

    def us(v):
        return v / 1000

    mean_dt = sum(dts) // len(dts)
    max_dt = max(abs(d) for d in dts)
    return ("ok sync n=%d miss L=%d R=%d | dt_us mean=%.1f max=%.1f | "
            "lat_us L=%.1f R=%.1f | exp_us L=%.1f R=%.1f" % (
                len(dts), miss_l, miss_r, us(mean_dt), us(max_dt),
                us(sum(lat_l) // len(lat_l)), us(sum(lat_r) // len(lat_r)),
                us(sum(wid_l) // len(wid_l)) if wid_l else -1,
                us(sum(wid_r) // len(wid_r)) if wid_r else -1))


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
    if cmd == "SYNC" and len(parts) <= 2:
        if running:
            return "err running"
        try:
            n = int(parts[1]) if len(parts) == 2 else 32
        except ValueError:
            return "err bad n"
        if not (1 <= n <= 1000):
            return "err bad n"
        return sync_check(n)
    if cmd == "LASER" and len(parts) == 3:
        if running:
            return "err running"
        pin = {"A": laser_a, "B": laser_b}.get(parts[1].upper())
        if pin is None or parts[2] not in ("0", "1"):
            return "err bad args"
        _laser(pin, int(parts[2]))
        return "ok"
    return "err unknown"


def main():
    btn_prev = 1
    buf = ""
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
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

        ch = sys.stdin.read(1) if poller.poll(0) else None
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
