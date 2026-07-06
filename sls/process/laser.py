"""Laser line extraction: dark-frame subtraction + per-row subpixel peak.

Works on *rectified* images so extracted points feed straight into row-wise
stereo matching. Strobing (A / B / dark) means each lit frame contains exactly
one laser line, so there is no X-crossing disambiguation to do here.

Per-row extraction assumes the line crosses image rows once, which holds for
both ±45° lines of the X over a smooth surface patch; rows where that fails
(specular blowout, occlusion, line locally horizontal) are rejected by the
quality gates and simply produce no sample.
"""

from __future__ import annotations

import numpy as np


def difference_image(lit: np.ndarray, dark: np.ndarray) -> np.ndarray:
    """Ambient-rejected laser image (float32, clipped at 0)."""
    return np.clip(lit.astype(np.float32) - dark.astype(np.float32), 0, None)


def extract_rows(
    diff: np.ndarray,
    min_intensity: float = 20.0,
    min_contrast: float = 3.0,
    window: int = 5,
) -> np.ndarray:
    """Per-row subpixel laser peak.

    For every image row, take the brightest column and refine it with an
    intensity-weighted centroid over ±window columns. Rows fail the gates when
    the peak is dim (< min_intensity) or not locally dominant (< min_contrast
    x the row median), i.e. no laser or ambient junk.

    Returns an (N, 2) float32 array of (row, col_subpixel).
    """
    h, w = diff.shape
    rows = np.arange(h)
    peak_col = np.argmax(diff, axis=1)
    peak_val = diff[rows, peak_col]
    row_med = np.median(diff, axis=1) + 1e-6

    ok = (peak_val >= min_intensity) & (peak_val >= min_contrast * row_med)
    # exclude peaks whose centroid window would fall off the image
    ok &= (peak_col >= window) & (peak_col < w - window)

    out = []
    offs = np.arange(-window, window + 1)
    for r in rows[ok]:
        c = peak_col[r]
        seg = diff[r, c - window : c + window + 1]
        sub = c + float((seg * offs).sum() / seg.sum())
        out.append((float(r), sub))
    return np.asarray(out, dtype=np.float32).reshape(-1, 2)
