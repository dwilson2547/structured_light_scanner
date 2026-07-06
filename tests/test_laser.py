import numpy as np

from sls.process.laser import difference_image, extract_rows


def synth_line(h=200, w=400, col_at=lambda r: 180.5 + 0.2 * r, sigma=1.5, amp=180.0):
    img = np.zeros((h, w), np.float32)
    cols = np.arange(w, dtype=np.float32)
    for r in range(h):
        img[r] = amp * np.exp(-0.5 * ((cols - col_at(r)) / sigma) ** 2)
    return img


def test_extract_recovers_subpixel_center():
    truth = lambda r: 120.3 + 0.15 * r
    diff = synth_line(h=100, col_at=truth)
    peaks = extract_rows(diff)
    assert len(peaks) > 90
    err = np.abs(peaks[:, 1] - np.array([truth(r) for r in peaks[:, 0]]))
    assert err.max() < 0.1


def test_difference_image_rejects_ambient():
    ambient = np.tile(np.linspace(30, 90, 400, dtype=np.float32), (100, 1))
    lit = np.clip(ambient + synth_line(h=100), 0, 255).astype(np.uint8)
    dark = ambient.astype(np.uint8)
    peaks = extract_rows(difference_image(lit, dark))
    assert len(peaks) > 90
    # ambient-only image yields (almost) nothing
    none_peaks = extract_rows(difference_image(dark, dark))
    assert len(none_peaks) == 0


def test_dim_rows_are_rejected():
    diff = synth_line(h=100, amp=5.0)  # below min_intensity
    assert len(extract_rows(diff)) == 0
