"""Single-camera laser bench test: live line-detection diagnostics.

Bench setup: one OV9281 free-running (no trigger box), both lasers on
continuously, the X projected on the desk. The HUD reports exactly what the
trim pots change — peak brightness, saturation, line width, contrast — plus
whether the production extractor (`extract_rows`) is actually picking the
line up. Capture a dark frame (`d`, block the lasers) to run the same
dark-subtraction the strobed pipeline will use.

Tuning targets: peak near but below 255, saturated fraction ~0, width a few
px (focus the line lens), contrast comfortably above the extractor's
min_contrast gate, extract-rows pickup high wherever a line crosses a row.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..capture.camera import Camera
from ..process.laser import difference_image, extract_rows

SAT_LEVEL = 250  # raw 8-bit value treated as saturated


@dataclass
class BenchResult:
    peak: float            # brightest pixel in the (dark-subtracted) image
    sat_frac: float        # fraction of *raw* pixels >= SAT_LEVEL
    contrast: float        # peak / median background
    width_px: float        # median horizontal run width of the line mask
    angles_deg: list[float]        # direction of each dominant Hough line
    lines: list[tuple[float, float]]  # (rho, theta) of those lines
    xing: tuple[float, float] | None  # X crossing point, if two lines found
    samples: np.ndarray    # (N, 2) extract_rows output on the diff image
    rows_frac: float       # fraction of image rows extract_rows accepted
    mask: np.ndarray       # uint8 line mask used for Hough/width


def _run_widths(mask: np.ndarray) -> np.ndarray:
    """Lengths of horizontal runs of 1s, over all rows."""
    padded = np.zeros((mask.shape[0], mask.shape[1] + 2), np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    starts = np.argwhere(d == 1)
    ends = np.argwhere(d == -1)
    return (ends[:, 1] - starts[:, 1]).astype(np.float32)


def _dominant_lines(
    mask: np.ndarray, max_lines: int = 2, min_angle_sep_deg: float = 15.0
) -> list[tuple[float, float]]:
    """Up to max_lines strongest Hough lines with distinct orientations."""
    thresh = max(50, int(0.2 * min(mask.shape)))
    found = cv2.HoughLines(mask * 255, 1, np.pi / 180.0, thresh)
    if found is None:
        return []
    out: list[tuple[float, float]] = []
    for rho, theta in found[:, 0, :]:
        deg = np.degrees(theta)
        sep_ok = all(
            min(abs(deg - np.degrees(t)) % 180.0,
                180.0 - abs(deg - np.degrees(t)) % 180.0) >= min_angle_sep_deg
            for _, t in out
        )
        if sep_ok:
            out.append((float(rho), float(theta)))
        if len(out) == max_lines:
            break
    return out


def _intersect(l1: tuple[float, float], l2: tuple[float, float]) -> tuple[float, float] | None:
    (r1, t1), (r2, t2) = l1, l2
    A = np.array([[np.cos(t1), np.sin(t1)], [np.cos(t2), np.sin(t2)]])
    if abs(np.linalg.det(A)) < 1e-6:
        return None
    x, y = np.linalg.solve(A, np.array([r1, r2]))
    return float(x), float(y)


def analyze(
    raw: np.ndarray,
    dark: np.ndarray | None = None,
    min_intensity: float = 40.0,
) -> BenchResult:
    """Line-detection diagnostics for one frame (pure; testable offline)."""
    diff = difference_image(raw, dark) if dark is not None else raw.astype(np.float32)
    peak = float(diff.max())
    sat_frac = float((raw >= SAT_LEVEL).mean())
    contrast = peak / (float(np.median(diff)) + 1e-6)

    mask = (diff >= max(min_intensity, 0.35 * peak)).astype(np.uint8)
    widths = _run_widths(mask)
    width_px = float(np.median(widths)) if len(widths) else 0.0

    lines = _dominant_lines(mask)
    angles = [(np.degrees(t) + 90.0) % 180.0 for _, t in lines]
    xing = _intersect(lines[0], lines[1]) if len(lines) == 2 else None

    samples = extract_rows(diff, min_intensity=min_intensity)
    rows_frac = len(samples) / raw.shape[0]

    return BenchResult(peak=peak, sat_frac=sat_frac, contrast=contrast,
                       width_px=width_px, angles_deg=angles, lines=lines,
                       xing=xing, samples=samples, rows_frac=rows_frac, mask=mask)


def _draw(raw: np.ndarray, res: BenchResult, dark_on: bool, exposure: int) -> np.ndarray:
    vis = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    vis[res.mask > 0, 1] = 255                       # line mask tinted green
    diag = float(np.hypot(*raw.shape))
    for rho, theta in res.lines:                     # Hough fits in blue
        a, b = np.cos(theta), np.sin(theta)
        p0 = np.array([a * rho, b * rho])
        p1 = (p0 + diag * np.array([-b, a])).astype(int)
        p2 = (p0 - diag * np.array([-b, a])).astype(int)
        cv2.line(vis, tuple(p1), tuple(p2), (255, 128, 0), 1)
    for r, c in res.samples[::4]:                    # extractor samples in red
        cv2.circle(vis, (int(round(c)), int(round(r))), 1, (0, 0, 255), -1)
    if res.xing is not None:
        cv2.circle(vis, (int(res.xing[0]), int(res.xing[1])), 8, (0, 255, 255), 2)

    ang = ", ".join(f"{a:.0f}" for a in res.angles_deg) or "-"
    hud = [
        f"peak {res.peak:.0f}  sat {res.sat_frac * 100:.2f}%  contrast {res.contrast:.0f}x",
        f"width {res.width_px:.1f}px  lines {len(res.lines)} @ {ang} deg",
        f"extract_rows {res.rows_frac * 100:.0f}% of rows  "
        f"dark {'ON' if dark_on else 'off'}  exp {exposure}",
    ]
    for i, text in enumerate(hud):
        cv2.putText(vis, text, (10, 28 + 26 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 3)
        cv2.putText(vis, text, (10, 28 + 26 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
    return vis


def bench(cam: Camera, min_intensity: float = 40.0, out_dir: Path = Path("bench")) -> None:
    cam.start()
    print("q quit | d grab dark frame (block lasers first) | c clear dark")
    print("s snapshot -> bench/ | e/E exposure down/up | f fps")
    dark: np.ndarray | None = None
    exposure = cam.get_exposure()
    n, t0 = 0, time.monotonic()
    try:
        while True:
            f = cam.read(timeout=1.0)
            if f is None:
                print("no frame — camera stalled? (still waiting)")
                continue
            raw = f.image
            res = analyze(raw, dark, min_intensity=min_intensity)
            vis = _draw(raw, res, dark is not None, exposure)
            n += 1
            cv2.imshow("sls bench", vis)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("d"):
                dark = raw.copy()
                print("dark frame captured — unblock the lasers")
            elif key == ord("c"):
                dark = None
            elif key in (ord("e"), ord("E")):
                exposure = (max(1, exposure // 2) if key == ord("e")
                            else min(5000, max(2, exposure * 2)))
                cam.set_manual_exposure(exposure)
                print(f"exposure -> {exposure}")
            elif key == ord("s"):
                out_dir.mkdir(parents=True, exist_ok=True)
                stem = out_dir / time.strftime("%Y%m%d-%H%M%S")
                cv2.imwrite(f"{stem}-raw.png", raw)
                cv2.imwrite(f"{stem}-annotated.png", vis)
                if dark is not None:
                    cv2.imwrite(f"{stem}-dark.png", dark)
                ang = ", ".join(f"{a:.1f}" for a in res.angles_deg) or "-"
                Path(f"{stem}-metrics.txt").write_text(
                    f"peak {res.peak:.1f}\nsat_frac {res.sat_frac:.4f}\n"
                    f"contrast {res.contrast:.1f}\nwidth_px {res.width_px:.2f}\n"
                    f"lines {len(res.lines)} @ {ang} deg\n"
                    f"rows_frac {res.rows_frac:.3f}\nexposure {exposure}\n"
                    f"dark_subtraction {dark is not None}\n")
                print(f"saved {stem}-*.png")
            elif key == ord("f"):
                dt = time.monotonic() - t0
                print(f"{n / dt:.1f} fps over {dt:.1f}s")
                n, t0 = 0, time.monotonic()
    finally:
        cam.stop()
        cv2.destroyAllWindows()
