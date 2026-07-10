"""Bench diagnostics on synthetic X-pattern frames."""

import cv2
import numpy as np

from sls.viz.bench import analyze


def synth_x(h: int = 240, w: int = 320, thickness: int = 3, peak: int = 220,
            ambient: int = 8) -> np.ndarray:
    """Two crossed diagonal lines over dim ambient, slightly blurred."""
    rng = np.random.default_rng(42)
    img = rng.uniform(0, ambient, (h, w)).astype(np.uint8)
    cv2.line(img, (0, 0), (w - 1, h - 1), peak, thickness)
    cv2.line(img, (0, h - 1), (w - 1, 0), peak, thickness)
    return cv2.GaussianBlur(img, (5, 5), 0)


def test_finds_both_lines_and_crossing():
    img = synth_x()
    res = analyze(img, min_intensity=30.0)
    assert len(res.lines) == 2
    # crossing near image centre
    assert res.xing is not None
    assert abs(res.xing[0] - 160) < 15 and abs(res.xing[1] - 120) < 15
    # diagonal-ish orientations, clearly separated
    a1, a2 = sorted(res.angles_deg)
    assert abs(a1 - a2) > 30


def test_metrics_in_sane_ranges():
    res = analyze(synth_x(), min_intensity=30.0)
    assert res.sat_frac == 0.0
    assert res.peak > 150
    assert res.contrast > 10
    # horizontal-run width: ~thickness / sin(line angle), plus blur
    assert 2.0 <= res.width_px <= 15.0
    assert res.rows_frac > 0.5  # extractor picks up most rows


def test_dark_subtraction_kills_ambient_only_scene():
    ambient = synth_x(peak=0, ambient=60)
    res = analyze(ambient, dark=ambient, min_intensity=30.0)
    assert res.lines == []
    assert len(res.samples) == 0


def test_no_lines_in_noise():
    rng = np.random.default_rng(0)
    img = rng.uniform(0, 15, (240, 320)).astype(np.uint8)
    res = analyze(img, min_intensity=30.0)
    assert res.lines == []
    assert res.rows_frac == 0.0
