---
tier: project
domain: robotics
---

# structured-light-scanner

Handheld structured-light 3D scanner proof-of-concept: two Arducam OV9281 global-shutter mono
cameras (hardware-triggered, 100 fps) + two strobed green line lasers in an X pattern, stereo
triangulation of the laser curves.

- **Rig design / CAD spec:** [`docs/hardware/handheld-rig.md`](docs/hardware/handheld-rig.md)
- **Software architecture:** [`docs/architecture.md`](docs/architecture.md)
- **Trigger firmware (Pi Pico):** [`firmware/trigger_pico/`](firmware/trigger_pico/)

## Quickstart

```bash
conda activate py313
pip install -e ".[dev]"

sls preview --left 0 --right 2           # live view, find your /dev/video indices
sls capture --session calib01 --free     # free-running capture of ChArUco views
sls calibrate --session calib01 --out calib/rig01
sls scan --session scan01 --calib calib/rig01   # triggered capture with strobing
sls process --session scan01 --calib calib/rig01 --out scan01.ply
```

## Hardware status

- [ ] Housing designed / printed
- [ ] Cameras in external-trigger mode (Arducam config tool)
- [ ] Pico flashed with `firmware/trigger_pico/main.py`, FSIN + laser MOSFETs wired
- [ ] Lenses focused at 350 mm, locked
- [ ] Stereo calibration done (rms < 0.3 px is the bar)

## Development

```bash
pytest            # math/extraction tests run without hardware
```
