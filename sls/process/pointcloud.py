"""Point cloud accumulation and binary PLY export."""

from __future__ import annotations

from pathlib import Path

import numpy as np


class CloudAccumulator:
    def __init__(self):
        self._chunks: list[np.ndarray] = []

    def add(self, xyz: np.ndarray, pose: np.ndarray | None = None) -> None:
        """Add (N,3) points, optionally transformed by a 4x4 rig pose."""
        if len(xyz) == 0:
            return
        if pose is not None:
            xyz = xyz @ pose[:3, :3].T + pose[:3, 3]
        self._chunks.append(np.asarray(xyz, dtype=np.float32))

    def points(self) -> np.ndarray:
        if not self._chunks:
            return np.empty((0, 3), dtype=np.float32)
        return np.concatenate(self._chunks, axis=0)


def write_ply(path: Path, xyz: np.ndarray) -> None:
    xyz = np.asarray(xyz, dtype="<f4")
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(xyz)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "end_header\n"
    )
    with open(path, "wb") as f:
        f.write(header.encode("ascii"))
        f.write(xyz.tobytes())


def read_ply(path: Path) -> np.ndarray:
    """Minimal reader for the files write_ply produces (for tests/tools)."""
    with open(path, "rb") as f:
        n = 0
        while True:
            line = f.readline().decode("ascii").strip()
            if line.startswith("element vertex"):
                n = int(line.split()[-1])
            if line == "end_header":
                break
        return np.frombuffer(f.read(n * 12), dtype="<f4").reshape(n, 3).copy()
