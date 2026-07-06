# Handheld rig — design spec (v1)

Target: tabletop objects (5–40 cm) at a **working distance of 250–500 mm, sweet spot 350 mm**.
Tethered to the desktop; onboard electronics are just the two cameras, two lasers, and the
trigger MCU.

## Geometry (the numbers CAD needs)

```
        ← 120 mm baseline →
   [cam L]                [cam R]
      \ 10°                / 10°          both cameras toe-in 10°
       \                  /
        \    [laser ×2]  /               lasers centered, rolled ±45°
         \      ||      /
          \     ||     /
           \    ||    /
            ×──────────  optical axes + laser cross intersect
                          at ~350 mm from the front face
```

| Parameter | Value | Why |
|---|---|---|
| Camera baseline | **120 mm** (lens centers) | ~0.1–0.2 mm depth noise at 350 mm with subpixel laser peaks |
| Toe-in | **10° each** (converging) | axes intersect at ~350 mm → max stereo overlap at the sweet spot |
| Camera roll/pitch | 0°, axes coplanar | keeps rectification well-conditioned |
| Laser modules | centered between cameras, **rolled +45° and −45°** | forms the X; identity is separated in time (strobing), not space |
| Laser vertical offset | stack them ~20 mm apart vertically, both aimed at the 350 mm axis crossing | they can't physically share one spot; a small offset is calibrated away |
| Laser fan angle | **60°** preferred (90° works, thinner power) | 60° fan spans ~400 mm of line at 350 mm — covers the whole FoV |

Stereo does the depth measurement, so **laser placement is not accuracy-critical** — only the
camera geometry is. Get the 120 mm / 10° right and rigid; the lasers just need to hit the scene.

### Optics sanity check

OV9281: 1/4" sensor, 1280×800, 3.0 µm pixels (active area 3.84 × 2.40 mm). With the common
Arducam stock M12 lens (~2.8 mm, ≈70° HFOV): footprint at 350 mm ≈ 480 mm wide — generous.
If your kit has interchangeable M12 lenses, a **4 mm lens (≈51° HFOV, ~330 mm footprint)** gives
~40% better resolution on tabletop objects and is worth trying; start with stock.

## Housing layout

Three assemblies: a **rigid camera bar**, a **laser pod**, and a **pistol grip**.

1. **Camera bar** — one printed monocoque, roughly 180 × 45 × 35 mm.
   - Two camera pockets with their mounting faces pre-angled at 10° toe-in (print the angle into
     the part; don't rely on adjustable mounts — adjustability is un-repeatability).
   - Arducam USB boards mount via their corner holes — **check the hole pattern on your exact
     board's drawing** (varies by model; typically M2 corners on a ~38 mm square board). Use
     heat-set inserts or print standoffs + self-tappers.
   - Lens barrels protrude through clearance holes in the front face; leave finger access to the
     M12 focus ring, add a small grub-screw boss to lock focus after setting it at 350 mm.
2. **Laser pod** — center of the bar, two 12 mm bores (verify your module barrel ⌀) as pinch
   clamps with M3 bolts, each bore rolled ±45°. Bores aimed parallel to the central axis is fine;
   fine-aim by rotating in the clamp before pinching.
3. **Grip** — pistol grip under the bar center. Hollow: route the trigger MCU (Pi Pico) and a
   small proto-area for the two laser MOSFETs inside the grip or a rear tray. One momentary
   button on the grip wired to the Pico (scan start/stop) is cheap and very ergonomic.
4. **Cable exit** — single strain-relieved exit at the rear bottom: 2× USB (cameras), 1× USB
   (Pico). Zip-tie anchor point inside.

### Print notes (these matter more than the shape)

- **Stiffness is calibration.** Any flex between the two cameras invalidates the stereo
  calibration. Print the bar flat, ≥4 perimeters, ≥40% infill; PETG or ABS/ASA over PLA (PLA
  creeps under warm cameras). If v1 flexes, bolt the printed pockets to a 2020 extrusion instead
  of reprinting thicker.
- Cameras and lasers dissipate a few watts total — add vent slots near the camera boards.
- Design the camera pockets so boards register against **machined datums of the part** (flat
  face + two pins/edges), not against screw positions.

## Electrical

| Item | Notes |
|---|---|
| Trigger MCU | Raspberry Pi Pico (3.3 V logic, matches camera trigger input) |
| Camera FSIN/trigger | one GPIO fanned to both cameras' trigger pins → truly simultaneous exposure. Verify trigger pin location & polarity on your Arducam model's docs; enable trigger mode with Arducam's config tool |
| Lasers | one N-MOSFET (or logic-level transistor) per laser off Pico GPIOs, so firmware can strobe them per-frame. Common ground with the Pico |
| Laser power | check module rating; most 12 mm modules take 3–5 V, ≤50 mA — can run from Pico VBUS through the MOSFETs |
| Strobe pattern (default) | 3-phase at 100 fps: frame 0 = laser A, frame 1 = laser B, frame 2 = both off (ambient). Solves ambient rejection *and* which-line-is-which in one move; effective 33 scan profiles/s per line |

## BOM (rig)

- 2× Arducam OV9281 USB global-shutter mono, external-trigger capable
- 2× green (520 nm) line laser modules, 60° fan, 12 mm barrel
- 1× Raspberry Pi Pico + 2× logic-level N-MOSFET (e.g. AO3400/2N7002) + resistors
- Heat-set inserts M2/M3, M3 bolts, momentary button, zip ties
- Printed: camera bar, laser clamps, grip
- Later/optional: 520 nm bandpass filters (M12 thread-in) if ambient rejection via strobing
  isn't enough; a ChArUco calibration board (print `docs/hardware/charuco.md` instructions —
  rigid backing, e.g. glued to glass or FR4)
