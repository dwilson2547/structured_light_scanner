import numpy as np

from sls.process.triangulate import depth_range_to_disparity, match_rows, triangulate

# Ideal rectified rig: f=933 px, cx=640, cy=400, baseline 120 mm.
F, CX, CY, B = 933.0, 640.0, 400.0, 0.120
Q = np.array([
    [1, 0, 0, -CX],
    [0, 1, 0, -CY],
    [0, 0, 0, F],
    [0, 0, -1 / -B, 0],  # Q[3,2] = -1/Tx with Tx = -B for left-reference rigs
], dtype=np.float64)


def project(pts):
    """world -> (row, x_l, x_r) for the ideal rectified pair."""
    X, Y, Z = pts[:, 0], pts[:, 1], pts[:, 2]
    x_l = F * X / Z + CX
    x_r = F * (X - B) / Z + CX
    row = F * Y / Z + CY
    return np.stack([np.round(row), x_l, x_r], axis=1).astype(np.float32)


def test_triangulate_roundtrip():
    rng = np.random.default_rng(0)
    pts = np.stack([
        rng.uniform(-0.1, 0.1, 50),
        rng.uniform(-0.1, 0.1, 50),
        rng.uniform(0.25, 0.5, 50),
    ], axis=1)
    rec = triangulate(project(pts), Q)
    # rounding the row quantizes Y slightly; X/Z are exact
    assert np.abs(rec[:, [0, 2]] - pts[:, [0, 2]]).max() < 1e-4
    assert np.abs(rec[:, 1] - pts[:, 1]).max() < 5e-4


def test_match_rows_joins_and_bounds():
    peaks_l = np.array([[10, 500.0], [11, 501.0], [12, 502.0], [20, 700.0]], np.float32)
    peaks_r = np.array([[10, 200.0], [12, 495.0], [20, 100.0], [30, 50.0]], np.float32)
    m = match_rows(peaks_l, peaks_r, min_disparity=1.0, max_disparity=400.0)
    # row 11 unmatched, row 30 unmatched, row 20 disparity 600 > max,
    # row 10 disparity 300 ok, row 12 disparity 7 ok
    assert m.shape == (2, 3)
    assert set(m[:, 0].astype(int)) == {10, 12}


def test_depth_range_to_disparity_consistent():
    d_min, d_max = depth_range_to_disparity(Q, z_near=0.25, z_far=0.50)
    for d, z in ((d_min, 0.50), (d_max, 0.25)):
        rec = triangulate(np.array([[CY, CX + d, CX]], np.float32), Q)
        assert abs(rec[0, 2] - z) < 1e-6
