"""ChArUco calibration target + per-camera intrinsic calibration."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

SQUARES_X, SQUARES_Y = 7, 5
ARUCO_DICT = cv2.aruco.DICT_4X4_50


def make_board(square_mm: float = 30.0, marker_mm: float = 22.0) -> cv2.aruco.CharucoBoard:
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    return cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y), square_mm / 1000.0, marker_mm / 1000.0, dictionary)


def export_board_png(out: Path, board: cv2.aruco.CharucoBoard, px_per_square: int = 200) -> None:
    size = (SQUARES_X * px_per_square, SQUARES_Y * px_per_square)
    img = board.generateImage(size, marginSize=px_per_square // 2)
    cv2.imwrite(str(out), img)


def detect_charuco(img: np.ndarray, board: cv2.aruco.CharucoBoard):
    """Returns (charuco_corners, charuco_ids), either None if nothing found."""
    detector = cv2.aruco.CharucoDetector(board)
    corners, ids, _marker_corners, _marker_ids = detector.detectBoard(img)
    return corners, ids


def calibrate_intrinsics(
    imgs: list[np.ndarray],
    board: cv2.aruco.CharucoBoard,
    min_corners: int = 8,
) -> tuple[np.ndarray, np.ndarray, float, list[int]]:
    """Per-camera intrinsic calibration from ChArUco views.

    Returns (K, dist, rms, used_indices) — used_indices are positions in `imgs`
    that had enough detected corners to use.
    """
    all_obj, all_img, used = [], [], []
    image_size = None
    for i, img in enumerate(imgs):
        if img is None:
            continue
        image_size = (img.shape[1], img.shape[0])
        corners, ids = detect_charuco(img, board)
        if corners is None or ids is None or len(ids) < min_corners:
            continue
        obj_pts, img_pts = board.matchImagePoints(corners, ids)
        if obj_pts is None or len(obj_pts) < min_corners:
            continue
        all_obj.append(obj_pts)
        all_img.append(img_pts)
        used.append(i)

    if len(used) < 4:
        raise RuntimeError(f"only {len(used)} usable ChArUco views (need >= 4) — "
                            f"capture more varied board poses")

    rms, K, dist, _rvecs, _tvecs = cv2.calibrateCamera(
        all_obj, all_img, image_size, None, None)
    return K, dist, rms, used
