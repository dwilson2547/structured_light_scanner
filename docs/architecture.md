# Architecture

Proof-of-concept pipeline: two hardware-triggered global-shutter mono cameras + two strobed
green line lasers in an X. Stereo triangulation of the laser curves gives metric 3D profiles
per frame; frame-to-frame registration turns profiles into a scan.

## Measurement principle

- Both cameras expose simultaneously (shared FSIN pulse from the Pico).
- Lasers strobe in a 3-phase pattern synchronized to frames: **A / B / dark**.
- For each lit frame, subtract the nearest dark frame → ambient-rejected laser image.
- Extract the laser curve at subpixel precision, per rectified image row.
- Match L/R curve points on the same rectified row → disparity → 3D point (OpenCV `Q` matrix).
- Depth accuracy is set by the *camera* geometry (120 mm baseline, calibrated); the lasers are
  only illumination, so their mounting doesn't need to be precise.

The X gives two independent profiles per cycle with different orientations, which is what makes
handheld registration (phase 2) tractable: two crossing curves constrain pose better than one.

## Pipeline stages

```
trigger (Pico fw) ──► capture ──► phase grouping ──► laser extraction ──► stereo
                      2× UVC       A/B/dark sets      subpixel centers     triangulation
                                                                              │
         PLY out ◄── point cloud accumulation ◄── registration (v1: static rig / turntable;
                                                   v2: ICP / cross-line pose)
```

## Package layout (`sls/`)

| Module | Responsibility |
|---|---|
| `capture/camera.py` | one UVC camera: V4L2 via OpenCV, threaded grab, mono format |
| `capture/trigger.py` | serial protocol to the Pico (start/stop, fps, strobe pattern, laser override) |
| `capture/session.py` | run a capture: trigger + both cameras → frame triplets on disk with metadata |
| `calib/intrinsics.py` | per-camera ChArUco intrinsic calibration |
| `calib/stereo.py` | stereo extrinsics + rectification maps; calibration bundle save/load |
| `process/laser.py` | dark-frame subtraction, mask, per-row subpixel peak extraction |
| `process/triangulate.py` | rectified L/R row matching → disparity → 3D |
| `process/pointcloud.py` | accumulation + PLY writer |
| `process/register.py` | frame-to-frame pose; v1 = identity (static rig), ICP hook for v2 |
| `viz/preview.py` | live two-camera preview with laser-line overlay |
| `cli.py` | `sls` entry point: `preview`, `capture`, `calibrate`, `scan`, `process` |

`firmware/trigger_pico/` holds the MicroPython firmware for the Pico.

## Data on disk

A capture session is a directory:

```
sessions/<name>/
  meta.json            # fps, pattern, camera ids, calibration ref, timestamps
  frames/              # {frame_idx:06d}_{L|R}.png  (8-bit mono)
```

Calibration bundle: `calib/<name>.npz` (K/dist per camera, R/T, rectification maps, Q) plus a
human-readable `calib/<name>.json` summary (rms errors, image size, date).

## Phasing

1. **Phase 0 (now)** — bench bring-up: preview, trigger, calibration, single-position profiles.
2. **Phase 1** — static rig + turntable or slow sweep: naive accumulation, first real clouds.
3. **Phase 2** — handheld: registration via ICP seeded by cross-line geometry; that's the
   interesting part.
