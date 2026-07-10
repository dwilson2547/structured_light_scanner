# Trigger firmware (Raspberry Pi Pico, MicroPython)

Generates the shared FSIN pulse for both cameras and strobes the two lasers in
phase with it (default pattern `AB0`: laser A / laser B / dark).

## Flash

1. Install MicroPython on the Pico (hold BOOTSEL, copy the official `.uf2`).
2. Copy `main.py` to the Pico (`mpremote cp main.py :main.py`), reboot.
3. Sanity check: `mpremote` REPL or `echo PING > /dev/ttyACM0` → `ok pong`.

## Wiring

| Pico pin | Goes to |
|---|---|
| GP2 | F (FSIN/trigger) pin of both cameras (fanned out) |
| GP3 | laser A MOSFET gate |
| GP4 | laser B MOSFET gate |
| GP5 | grip button (other leg to GND) |
| GP6 | S (strobe output) of the LEFT camera |
| GP7 | S (strobe output) of the RIGHT camera |
| GND | camera G pins, laser supplies — one common ground |

The trigger is rising-edge, minimum 2 us high (`FSIN_PULSE_US = 100` is
plenty), 3.3 V logic — Arducam's own docs drive F straight from an RPi GPIO.
Before wiring the strobe pins, confirm with a meter that the strobe high
level is 3.3 V — the Pico's GPIOs are not 5 V tolerant.

## Laser driver circuit (complete spec)

Supply: Pico VBUS (5 V) → 3.3 V LDO → laser rail. Each laser is switched
**low-side by an N-channel MOSFET**. Per laser:

```
3.3V rail ──── laser +      laser − ──── drain (N-ch)
                                         source ──── GND
              Pico GP3/GP4 ──── gate ── 10k ── GND
```

- Gate **pulldown 10k to GND**: guarantees lasers are OFF while the Pico is
  unpowered, booting, or its pins are floating.
- Logic is **active-high** (gate high = laser on); `LASER_ACTIVE_LOW = False`
  in `main.py` matches this. A high-side P-channel build (source to rail,
  10k gate pull-up, active-low) also works — flip the flag if so.
- Do **not** put an N-channel on the high side (source to rail): its body
  diode conducts rail→laser permanently and the gate can never rise above
  the source, so it's stuck on regardless of GPIO (learned the hard way
  2026-07-07 — symptom: laser always lit at rail-minus-0.5 V ≈ 2.8 V).
- Vgs(th) matters: at 3.3 V drive, a ~2.3 V threshold part has ~1 V of
  overdrive. **Measured 2026-07-08: not enough.** Vgs(th)=2.32 V parts
  dropped Vds = 1.1 V at these laser currents — the lasers saw only ~2.2 V
  (one sputtered, one stayed dark). Use true logic-level parts
  (Vgs(th) ≤ ~2 V: IRLZ44N, AO3400), or the BJT alternative below.

Expected meter readings (firmware idle, lasers connected): gate = 0 V,
drain ≈ 3.3 V (laser pulls it up, no current flowing), laser dark.
`LASER A 1` → gate 3.3 V, drain near 0 V, laser lit. A drain stuck at
0.5 V+ while on means the switch isn't saturating.

### NPN BJT alternative (same low-side position, no logic change)

Any small NPN rated ≥ 500 mA (2N2222/PN2222, S8050, BC337, 2N4401 — not
BC547-class, too small). A saturated BJT drops ~0.2–0.3 V independent of
the 3.3 V drive limitation, so the laser sees ~3.0 V. Per laser:

```
3.3V rail ──── laser +      laser − ──── collector
                                         emitter ──── GND
              Pico GP3/GP4 ── 470Ω ── base ── 10k ── GND
```

- 470 Ω base resistor: ~5.5 mA base drive from the 3.3 V GPIO — within the
  RP2040 pin budget, saturates 150–250 mA of collector current. If the
  collector won't pull below ~0.4 V when on, drop it to 330 Ω.
- 10 k base pulldown: lasers stay OFF while the Pico is unpowered/booting.
- Logic stays active-high (`LASER_ACTIVE_LOW = False`) — no firmware change.
- Pinouts differ between NPN families (2N2222 vs BC337 leg order) — verify
  with a component tester before soldering.

## Enabling external-trigger mode (Linux)

No Windows config tool needed: the module's firmware repurposes the standard
UVC `exposure_dynamic_framerate` control as the trigger-mode switch (AMCap
shows the same bit as "low-brightness compensation"). Per camera:

```bash
v4l2-ctl -d /dev/video0 -c auto_exposure=1            # manual exposure
v4l2-ctl -d /dev/video0 -c exposure_time_absolute=20  # bench operating point
v4l2-ctl -d /dev/video0 -c gain=0
v4l2-ctl -d /dev/video0 -c exposure_dynamic_framerate=1   # trigger mode ON
```

Set `exposure_dynamic_framerate=0` to return to free-running. In trigger
mode the stream stalls until FSIN pulses arrive, so enable it only once the
Pico is wired. The setting does not survive a power cycle / re-enumeration —
re-apply after every `usbipd attach`.

## Verifying camera sync (`SYNC`)

> **Measured 2026-07-07: dead end on the current modules.** The S pad is the
> OV9281's FSTROBE pin, which needs a sensor-register enable (0x3006) that
> the Sonix USB-bridge firmware never performs — the pin sits at a constant
> 3.3 V through exposures, in both free-run and trigger mode. `SYNC` reports
> `miss` on every frame. Use the optical method instead:
> `python scripts/sync_sweep.py` maps both exposure windows by sweeping a
> laser flash across them (no alignment needed, ~tens-of-µs resolution).
> `SYNC` is kept for modules whose strobe actually works.

In principle the camera's strobe output is high while the sensor is exposing,
so with both strobes wired to GP6/GP7 the Pico can measure exposure timing
directly:

```bash
sls sync                 # or: echo "SYNC 32" > /dev/ttyACM0
# ok sync n=32 miss L=0 R=0 | dt_us mean=0.4 max=1.1 | lat_us L=88.2 R=88.5 | exp_us L=2001.0 R=2002.0
```

- `dt` — left-minus-right exposure-start skew. This is the "do both cameras
  fire at the same time" number; expect single-digit µs off a shared FSIN.
- `lat` — FSIN edge → exposure start, per camera.
- `exp` — strobe width = actual exposure time (cross-check against the UVC
  exposure setting).
- `miss` — frames where a strobe never rose: wiring problem or a camera not
  in external-trigger mode. This makes `SYNC` a useful bring-up smoke test
  before any video capture.

The measurement busy-polls the GPIO input register in viper-compiled code
(both pins sampled in one atomic 32-bit read, ~sub-µs resolution, no
channel-ordering bias); pin IRQs in MicroPython would add tens of µs of
scheduling jitter.
