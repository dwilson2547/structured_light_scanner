# Bench testing: lasers + one camera, before rig assembly

Goal: verify line pickup and tune the cheap laser modules (trim pot = drive
current, rotatable lens = line focus) against real numbers, with everything
loose on the desk. No Pico, no trigger, no calibration needed.

## Getting the camera into WSL2

The WSL kernel already has `uvcvideo` and USB/IP support as modules. The
Windows side needs [usbipd-win](https://github.com/dorssel/usbipd-win) once:

```powershell
# elevated PowerShell
winget install usbipd
usbipd list                      # find the camera busid, e.g. 3-2
usbipd bind --busid <busid>      # once per device (admin)
usbipd attach --wsl --busid <busid>   # per session (no admin needed)
```

Then in WSL:

```bash
ls /dev/video*          # camera should appear as /dev/video0 (+ a metadata node)
sudo usermod -aG video $USER   # once, if permission denied; re-login after
```

`usbipd attach` must be re-run after unplugging or a WSL restart
(`--auto-attach` keeps it sticky).

**Bandwidth caveat (measured 2026-07-06):** the USB/IP tunnel truncates
uncompressed frames — YUYV/GREY at any size and even MJPG at 1280x800 arrive
with only the top rows valid. **MJPG 640x480 is the largest intact mode**
(~94 fps), so `sls bench` defaults to it. JPEG compression adds a little
noise to the subpixel centroid; fine for bench tuning, but rig-phase strobed
capture at 1280x800 GREY will need either a native Linux host or revisiting
the tunnel (usbipd MTU/kernel, or camera on a Pi forwarding frames).

**Dual-camera caveat (measured 2026-07-07):** both cameras sustain MJPG
640x480 at ~90 fps *concurrently* through the tunnel — but only if their
streams start at different times. Two STREAMONs in the same instant knock
one camera off the virtual bus entirely (it re-enumerates; fix with
`usbipd detach --busid <id>` + re-attach). `Camera.start()` serializes
stream starts with a 1 s gap to prevent this; keep that in mind before
"optimizing" it away or starting cameras from parallel scripts.

## Running the bench

```bash
sls bench            # or --cam N if it didn't land on /dev/video0
```

Setup: camera on a mini tripod / propped ~350 mm from the desk, X pattern in
frame. Room lights however you'll realistically scan.

Live overlay: green = thresholded line mask, blue = Hough line fits,
red dots = what `extract_rows` (the production extractor) accepted,
yellow circle = X crossing.

Keys: `d` grab dark frame (block the lasers first — enables the same
dark-subtraction the strobed pipeline uses), `c` clear it, `e`/`E` exposure
down/up, `s` snapshot + metrics to `bench/`, `f` fps, `q` quit.

## What to tune toward

| HUD number | Target | Knob |
|---|---|---|
| peak | 200–250, not pinned at 255 | trim pot down / exposure down |
| sat | ~0.00% (blooming fattens the line) | same |
| contrast | ≥ 3x with room lights on (extractor gate) | exposure *down*, pot up |
| width | as small as focus allows, stable along the line | rotate line lens |
| extract_rows % | high wherever a line crosses rows | everything above |

The winning combination is usually **short exposure + bright laser**: ambient
scales down with exposure, the laser doesn't (much). Drive exposure down with
`e` until the desk goes nearly black and only the lines remain — that's the
regime the strobed A/B/dark scheme will operate in.

Things worth checking while it's all loose on the bench:

- **Trim pot range**: does min→max drive actually change peak/width usefully,
  or is it saturated at both ends?
- **Line uniformity**: intensity falloff toward the ends of each line
  (cheap cylinder lenses often fade badly off-axis).
- **Speckle**: is the extracted line (red dots) jittery frame-to-frame on a
  matte surface? Snapshot a few frames and compare.
- **Warm-up drift**: cheap modules dim/brighten over the first minutes; leave
  it running and watch peak.
- **Dark-subtraction win**: compare extract_rows % with and without `d` —
  this is the ambient-rejection margin the strobing buys.
