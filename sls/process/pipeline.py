"""Offline processing: session on disk + calibration -> point cloud.

Walks the strobe cycles of a session, pairs each lit frame with the dark
frame of its own cycle, rectifies, extracts, matches, triangulates.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..calib.stereo import CalibBundle
from ..capture.session import SessionMeta, frame_path
from ..capture.trigger import PATTERN_PHASES
from .laser import difference_image, extract_rows
from .pointcloud import CloudAccumulator
from .register import IdentityRegistration
from .triangulate import depth_range_to_disparity, match_rows, triangulate


def _load_pair(sess: Path, idx: int) -> tuple[np.ndarray, np.ndarray] | None:
    pl = frame_path(sess, idx, "L")
    pr = frame_path(sess, idx, "R")
    if not pl.exists() or not pr.exists():
        return None
    return (
        cv2.imread(str(pl), cv2.IMREAD_GRAYSCALE),
        cv2.imread(str(pr), cv2.IMREAD_GRAYSCALE),
    )


def process_session(
    sess: Path,
    calib: CalibBundle,
    z_near: float = 0.20,
    z_far: float = 0.60,
    registration=None,
) -> np.ndarray:
    """Returns (N, 3) points in meters, rectified-left frame of cycle 0."""
    meta = SessionMeta.load(sess / "meta.json")
    phases = PATTERN_PHASES[meta.pattern]
    cycle_len = len(phases)
    if "dark" not in phases:
        raise ValueError(
            f"pattern {meta.pattern!r} has no dark phase; scan with AB0 or A0")
    dark_off = phases.index("dark")

    (map_l, map_r) = calib.rectify_maps()
    d_min, d_max = depth_range_to_disparity(calib.Q, z_near, z_far)
    registration = registration or IdentityRegistration()
    acc = CloudAccumulator()

    n_cycles = meta.n_frames // cycle_len
    for cyc in range(n_cycles):
        base = cyc * cycle_len
        dark = _load_pair(sess, base + dark_off)
        if dark is None:
            continue
        dark_l = cv2.remap(dark[0], *map_l, cv2.INTER_LINEAR)
        dark_r = cv2.remap(dark[1], *map_r, cv2.INTER_LINEAR)
        pose = registration.pose(cyc)

        for off, phase in enumerate(phases):
            if phase == "dark":
                continue
            lit = _load_pair(sess, base + off)
            if lit is None:
                continue
            lit_l = cv2.remap(lit[0], *map_l, cv2.INTER_LINEAR)
            lit_r = cv2.remap(lit[1], *map_r, cv2.INTER_LINEAR)
            peaks_l = extract_rows(difference_image(lit_l, dark_l))
            peaks_r = extract_rows(difference_image(lit_r, dark_r))
            matches = match_rows(peaks_l, peaks_r, min_disparity=d_min, max_disparity=d_max)
            acc.add(triangulate(matches, calib.Q), pose=pose)

    return acc.points()
