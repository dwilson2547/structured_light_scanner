"""Frame-to-frame registration.

Phase 1 (static rig / turntable): identity — all profiles share the rig frame.
Phase 2 (handheld): estimate rig motion between strobe cycles. The planned
approach seeds ICP with the cross-line constraint: two profiles of known
relative orientation per cycle constrain 5 of 6 DoF against a smooth surface.
Open3D ICP slots in here; kept out of the deps until phase 2.
"""

from __future__ import annotations

import numpy as np


class IdentityRegistration:
    """Every frame already in the world frame (rig static, or turntable with
    known rotation applied upstream)."""

    def pose(self, cycle_index: int) -> np.ndarray:
        return np.eye(4)


class TurntableRegistration:
    """Known-rate turntable about a calibrated axis.

    axis_point/axis_dir define the rotation axis in the rig (rectified-left)
    frame; deg_per_cycle is the table step between strobe cycles.
    """

    def __init__(self, axis_point: np.ndarray, axis_dir: np.ndarray, deg_per_cycle: float):
        self.p = np.asarray(axis_point, dtype=np.float64)
        d = np.asarray(axis_dir, dtype=np.float64)
        self.d = d / np.linalg.norm(d)
        self.deg = deg_per_cycle

    def pose(self, cycle_index: int) -> np.ndarray:
        theta = np.deg2rad(self.deg * cycle_index)
        k = self.d
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        R = np.eye(3) + np.sin(theta) * K + (1 - np.cos(theta)) * (K @ K)
        pose = np.eye(4)
        pose[:3, :3] = R
        pose[:3, 3] = self.p - R @ self.p
        return pose
