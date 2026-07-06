"""Row-wise stereo matching of laser peaks + disparity -> 3D.

Inputs are per-row subpixel peaks from rectified left/right images of the
same strobe phase. On rectified images corresponding points share a row, so
matching is a join on row index. Disparity d = x_left - x_right, and 3D comes
from the rectification Q matrix; the result is in the rectified-left camera
frame, in the units of the calibration T (meters).
"""

from __future__ import annotations

import numpy as np


def match_rows(
    peaks_l: np.ndarray,
    peaks_r: np.ndarray,
    min_disparity: float = 1.0,
    max_disparity: float | None = None,
) -> np.ndarray:
    """Join (row, col) peak lists on row. Returns (N, 3): row, x_l, x_r.

    min/max disparity bound the working volume — with a converging rig
    calibrated by stereoRectify, far points have small disparity and near
    points large; use them to reject spurious matches outside 250–500 mm.
    """
    if len(peaks_l) == 0 or len(peaks_r) == 0:
        return np.empty((0, 3), dtype=np.float32)
    rl = peaks_l[:, 0].astype(np.int64)
    rr = peaks_r[:, 0].astype(np.int64)
    common, il, ir = np.intersect1d(rl, rr, return_indices=True)
    x_l = peaks_l[il, 1]
    x_r = peaks_r[ir, 1]
    d = x_l - x_r
    ok = d >= min_disparity
    if max_disparity is not None:
        ok &= d <= max_disparity
    return np.stack([common[ok].astype(np.float32), x_l[ok], x_r[ok]], axis=1)


def triangulate(matches: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """(row, x_l, x_r) -> (N, 3) XYZ via the 4x4 disparity-to-depth matrix Q."""
    if len(matches) == 0:
        return np.empty((0, 3), dtype=np.float32)
    row, x_l, x_r = matches[:, 0], matches[:, 1], matches[:, 2]
    d = x_l - x_r
    homog = np.stack([x_l, row, d, np.ones_like(d)], axis=1)  # (N, 4)
    pts = homog @ Q.T
    return (pts[:, :3] / pts[:, 3:4]).astype(np.float32)


def depth_range_to_disparity(Q: np.ndarray, z_near: float, z_far: float) -> tuple[float, float]:
    """Convert a working-depth window (meters) into (min_disparity, max_disparity).

    From Q: Z = -Q[2,3] / (d + Q[3,3]*W)... in the standard stereoRectify form
    Z = f*B / d with f = Q[2,3] and 1/B = Q[3,2], so d = f*B/Z.
    """
    f = Q[2, 3]
    inv_b = -Q[3, 2]
    fB = abs(f / inv_b) if inv_b != 0 else abs(f)
    return fB / z_far, fB / z_near
