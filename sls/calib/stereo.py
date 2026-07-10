"""Stereo extrinsics + rectification; calibration bundle save/load.

Bundle on disk (see docs/architecture.md): `<stem>.npz` holds the arrays,
`<stem>.json` is a human-readable summary (rms, baseline, image size, date).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .intrinsics import detect_charuco


@dataclass
class CalibBundle:
    K_l: np.ndarray
    dist_l: np.ndarray
    K_r: np.ndarray
    dist_r: np.ndarray
    R: np.ndarray
    T: np.ndarray
    R1: np.ndarray
    R2: np.ndarray
    P1: np.ndarray
    P2: np.ndarray
    Q: np.ndarray
    image_size: tuple[int, int]
    rms_stereo: float

    def rectify_maps(self):
        """(map_l, map_r), each an (mapx, mapy) pair for cv2.remap."""
        map_l = cv2.initUndistortRectifyMap(
            self.K_l, self.dist_l, self.R1, self.P1, self.image_size, cv2.CV_32FC1)
        map_r = cv2.initUndistortRectifyMap(
            self.K_r, self.dist_r, self.R2, self.P2, self.image_size, cv2.CV_32FC1)
        return map_l, map_r

    def save(self, stem: Path) -> None:
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            str(stem.with_suffix(".npz")),
            K_l=self.K_l, dist_l=self.dist_l, K_r=self.K_r, dist_r=self.dist_r,
            R=self.R, T=self.T, R1=self.R1, R2=self.R2, P1=self.P1, P2=self.P2, Q=self.Q,
            image_size=np.array(self.image_size), rms_stereo=self.rms_stereo,
        )
        summary = {
            "rms_stereo": self.rms_stereo,
            "baseline_mm": float(np.linalg.norm(self.T) * 1000),
            "image_size": list(self.image_size),
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        stem.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")

    @staticmethod
    def load(stem: Path) -> "CalibBundle":
        stem = Path(stem)
        data = np.load(str(stem.with_suffix(".npz")))
        return CalibBundle(
            K_l=data["K_l"], dist_l=data["dist_l"], K_r=data["K_r"], dist_r=data["dist_r"],
            R=data["R"], T=data["T"], R1=data["R1"], R2=data["R2"],
            P1=data["P1"], P2=data["P2"], Q=data["Q"],
            image_size=tuple(int(x) for x in data["image_size"]),
            rms_stereo=float(data["rms_stereo"]),
        )


def _matched_points(img_l, img_r, board, min_corners: int):
    """Detect ChArUco corners on both images and return object/image points
    for only the corner IDs seen by *both* cameras in this view, aligned by ID."""
    corners_l, ids_l = detect_charuco(img_l, board)
    corners_r, ids_r = detect_charuco(img_r, board)
    if ids_l is None or ids_r is None:
        return None
    ids_l_flat = ids_l.flatten()
    ids_r_flat = ids_r.flatten()
    common = np.intersect1d(ids_l_flat, ids_r_flat)
    if len(common) < min_corners:
        return None
    idx_l = np.array([np.flatnonzero(ids_l_flat == c)[0] for c in common])
    idx_r = np.array([np.flatnonzero(ids_r_flat == c)[0] for c in common])
    obj_pts, img_pts_l = board.matchImagePoints(corners_l[idx_l], ids_l[idx_l])
    _, img_pts_r = board.matchImagePoints(corners_r[idx_r], ids_r[idx_r])
    if obj_pts is None or len(obj_pts) < min_corners:
        return None
    return obj_pts, img_pts_l, img_pts_r


def calibrate_stereo(
    imgs_l: list[np.ndarray],
    imgs_r: list[np.ndarray],
    board: cv2.aruco.CharucoBoard,
    K_l: np.ndarray,
    dist_l: np.ndarray,
    K_r: np.ndarray,
    dist_r: np.ndarray,
    min_corners: int = 8,
) -> CalibBundle:
    all_obj, all_img_l, all_img_r = [], [], []
    image_size = None
    for img_l, img_r in zip(imgs_l, imgs_r):
        if img_l is None or img_r is None:
            continue
        image_size = (img_l.shape[1], img_l.shape[0])
        matched = _matched_points(img_l, img_r, board, min_corners)
        if matched is None:
            continue
        obj_pts, img_pts_l, img_pts_r = matched
        all_obj.append(obj_pts)
        all_img_l.append(img_pts_l)
        all_img_r.append(img_pts_r)

    if len(all_obj) < 4:
        raise RuntimeError(f"only {len(all_obj)} usable synchronized ChArUco views "
                            f"(need >= 4) — capture more varied board poses")

    rms, K_l, dist_l, K_r, dist_r, R, T, _E, _F = cv2.stereoCalibrate(
        all_obj, all_img_l, all_img_r, K_l, dist_l, K_r, dist_r, image_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
    )
    R1, R2, P1, P2, Q, _roi1, _roi2 = cv2.stereoRectify(
        K_l, dist_l, K_r, dist_r, image_size, R, T, alpha=0)

    return CalibBundle(
        K_l=K_l, dist_l=dist_l, K_r=K_r, dist_r=dist_r,
        R=R, T=T, R1=R1, R2=R2, P1=P1, P2=P2, Q=Q,
        image_size=image_size, rms_stereo=rms,
    )
