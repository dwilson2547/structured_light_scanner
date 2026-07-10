"""Optical camera-sync verification: map both cameras' exposure windows in time.

Why this exists: the S (strobe) pad on these Arducam UVC OV9281 modules is the
sensor's FSTROBE pin, which the USB bridge firmware never enables — it sits at
a constant 3.3 V (measured 2026-07-07; Arducam forum confirms). So the Pico
`SYNC` command can't see exposures electrically. Instead we measure optically:

  For each delay d, the Pico pulses FSIN and flashes laser A for 500 us
  starting d microseconds after the trigger. A frame is only bright if the
  flash overlapped that camera's exposure window. Sweeping d traces out
  brightness-vs-delay; the rising edge is exposure start, per camera, and
  the offset between the two cameras' edges is their trigger skew.

Both cameras see the *same physical flash* each frame, so Pico timing jitter
widens the edges but cannot bias the skew. Resolution ~ step size / SNR.

No optical alignment needed — any laser scatter that lands in both cameras'
view is enough (we measure whole-frame mean brightness). Prerequisites:
laser A driven by the Pico's GP3 MOSFET, cameras attached, Pico flashed.

Usage:
    python scripts/sync_sweep.py [--left 0] [--right 2] [--repeats 3]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sls.capture.camera import Camera  # noqa: E402

PULSE_US = 500
DELAYS_US = list(range(-1000, 3600, 250))
LASER_ACTIVE_LOW = False  # low-side N-ch drivers; keep in step with firmware

PICO_SWEEP = """
from machine import Pin
import time
ON, OFF = {on}, {off}
fsin = Pin(2, Pin.OUT, value=0)
laser = Pin(3, Pin.OUT, value=OFF)
delays = {delays}
time.sleep_ms(500)
for d in delays:
    if d < 0:
        laser.value(ON)
        time.sleep_us(-d)
        fsin.value(1); time.sleep_us(100); fsin.value(0)
        rem = {pulse} + d - 100
        if rem > 0:
            time.sleep_us(rem)
        laser.value(OFF)
    else:
        fsin.value(1); time.sleep_us(100); fsin.value(0)
        if d > 100:
            time.sleep_us(d - 100)
        laser.value(ON)
        time.sleep_us({pulse})
        laser.value(OFF)
    time.sleep_ms(150)
print("sweep done")
"""


def v4l2(dev: int, *ctrls: str) -> None:
    subprocess.run(["v4l2-ctl", "-d", f"/dev/video{dev}"]
                   + [x for c in ctrls for x in ("-c", c)], check=True)


def edge(delays: np.ndarray, bright: np.ndarray, rising: bool) -> float:
    """Delay of the 50% crossing, linearly interpolated."""
    lo = bright[delays <= -PULSE_US].mean()          # flash fully before exposure
    hi = np.percentile(bright, 90)
    half = (lo + hi) / 2.0
    above = bright >= half
    idx = np.flatnonzero(above[:-1] != above[1:])
    if len(idx) == 0:
        return float("nan")
    i = idx[0] if rising else idx[-1]
    b0, b1 = bright[i], bright[i + 1]
    frac = (half - b0) / (b1 - b0) if b1 != b0 else 0.5
    return float(delays[i] + frac * (delays[i + 1] - delays[i]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", type=int, default=0)
    ap.add_argument("--right", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--gain", type=int, default=50, help="high gain: scatter, not lines")
    ap.add_argument("--exposure", type=int, default=20)
    args = ap.parse_args()

    delays = DELAYS_US * args.repeats
    for dev in (args.left, args.right):
        v4l2(dev, "auto_exposure=1", f"exposure_time_absolute={args.exposure}",
             f"gain={args.gain}", "exposure_dynamic_framerate=1")

    cams = {"L": Camera(args.left, width=640, height=480, fps=100, fourcc="MJPG"),
            "R": Camera(args.right, width=640, height=480, fps=100, fourcc="MJPG")}
    for c in cams.values():
        c.start()
    time.sleep(1.0)
    for c in cams.values():
        c.flush()  # trigger mode: no frames until the sweep pulses FSIN

    mpremote = str(Path(sys.executable).parent / "mpremote")
    pico = subprocess.Popen(
        [mpremote, "connect", "/dev/ttyACM0", "exec",
         PICO_SWEEP.format(delays=delays, pulse=PULSE_US,
                           on=int(not LASER_ACTIVE_LOW),
                           off=int(LASER_ACTIVE_LOW))],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # frame index k == sweep step k (queues flushed, one frame per FSIN pulse)
    bright: dict[str, dict[int, float]] = {"L": {}, "R": {}}
    for _ in delays:
        for side, cam in cams.items():
            f = cam.read(timeout=5.0)
            if f is not None:
                bright[side][f.index] = float(f.image.mean())
    for c in cams.values():
        c.stop()
    out, _ = pico.communicate(timeout=30)
    if "sweep done" not in out:
        print(f"WARNING: pico sweep did not finish cleanly:\n{out}")

    uniq = np.array(sorted(set(DELAYS_US)), dtype=float)
    results = {}
    for side in ("L", "R"):
        got = bright[side]
        per_delay = [np.mean([got[k] for k in range(len(delays))
                              if k in got and delays[k] == d] or [np.nan])
                     for d in uniq]
        curve = np.array(per_delay)
        n_got = len(got)
        # the 50% crossing of the overlap ramp sits half a flash-width before
        # the true exposure edge; shift both crossings by +PULSE/2
        rise = edge(uniq, curve, rising=True)
        fall = edge(uniq, curve, rising=False)
        results[side] = (rise, fall, curve, n_got)
        print(f"{side}: {n_got}/{len(delays)} frames, exposure starts at "
              f"FSIN+{rise + PULSE_US / 2:.0f} us, ends ~FSIN+"
              f"{fall + PULSE_US / 2:.0f} us (width ~{fall - rise:.0f} us)")

    span = max(np.nanmax(results[s][2]) for s in "LR")
    base = min(np.nanmin(results[s][2]) for s in "LR")
    if span - base < 2.0:
        print("\nNO SIGNAL: brightness never rose above baseline — is laser A "
              "on GP3 lit, and does its scatter reach both cameras?")
        return
    skew = results["L"][0] - results["R"][0]
    print(f"\nexposure-start skew L-R: {skew:+.0f} us "
          f"(sweep step {uniq[1] - uniq[0]:.0f} us)")


if __name__ == "__main__":
    main()
