"""Capture sessions: run the trigger + both cameras, write frames + metadata to disk.

Session directory layout (see docs/architecture.md):

    sessions/<name>/
      meta.json
      frames/{idx:06d}_{L|R}.png
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from .camera import Camera
from .trigger import TriggerBox


@dataclass
class SessionMeta:
    name: str
    fps: int
    pattern: str  # strobe pattern, or "free" for untriggered capture
    left_device: int
    right_device: int
    n_frames: int = 0
    started_at: str = ""
    calib: str = ""
    notes: str = ""
    dropped: list[int] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2) + "\n")

    @staticmethod
    def load(path: Path) -> "SessionMeta":
        return SessionMeta(**json.loads(path.read_text()))


def session_dir(root: Path, name: str) -> Path:
    d = root / name
    (d / "frames").mkdir(parents=True, exist_ok=True)
    return d


def frame_path(sess: Path, idx: int, side: str) -> Path:
    return sess / "frames" / f"{idx:06d}_{side}.png"


def run_triggered(
    root: Path,
    name: str,
    left: Camera,
    right: Camera,
    trigger: TriggerBox,
    fps: int = 100,
    pattern: str = "AB0",
    duration_s: float = 10.0,
) -> SessionMeta:
    """Hardware-triggered capture. Frames are paired by grab index, which is
    valid because both queues are flushed immediately before START and every
    exposure comes from the shared FSIN pulse."""
    sess = session_dir(root, name)
    meta = SessionMeta(
        name=name, fps=fps, pattern=pattern,
        left_device=left.device, right_device=right.device,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    left.start()
    right.start()
    # let UVC pipelines settle on any free-running frames, then align counters
    time.sleep(0.5)
    left.flush()
    right.flush()

    trigger.start(fps, pattern)
    t_end = time.monotonic() + duration_s
    idx = 0
    try:
        while time.monotonic() < t_end:
            fl = left.read(timeout=1.0)
            fr = right.read(timeout=1.0)
            if fl is None or fr is None:
                meta.dropped.append(idx)
                idx += 1
                continue
            if fl.index != fr.index:
                # one side dropped a frame inside the UVC stack; resync by
                # discarding from the side that is ahead
                meta.dropped.append(idx)
                while fl.index < fr.index and fl is not None:
                    fl = left.read(timeout=1.0)
                while fr is not None and fl is not None and fr.index < fl.index:
                    fr = right.read(timeout=1.0)
                if fl is None or fr is None:
                    idx += 1
                    continue
            cv2.imwrite(str(frame_path(sess, idx, "L")), fl.image)
            cv2.imwrite(str(frame_path(sess, idx, "R")), fr.image)
            idx += 1
    finally:
        trigger.stop()
        left.stop()
        right.stop()

    meta.n_frames = idx
    meta.save(sess / "meta.json")
    return meta


def run_free(
    root: Path,
    name: str,
    left: Camera,
    right: Camera,
    n_frames: int = 40,
    interval_s: float = 0.5,
) -> SessionMeta:
    """Free-running capture for calibration: grabs a loosely-synced pair every
    `interval_s` (a static ChArUco board doesn't need hardware sync)."""
    sess = session_dir(root, name)
    meta = SessionMeta(
        name=name, fps=0, pattern="free",
        left_device=left.device, right_device=right.device,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    left.start()
    right.start()
    idx = 0
    try:
        while idx < n_frames:
            time.sleep(interval_s)
            left.flush()
            right.flush()
            fl = left.read()
            fr = right.read()
            if fl is None or fr is None:
                continue
            cv2.imwrite(str(frame_path(sess, idx, "L")), fl.image)
            cv2.imwrite(str(frame_path(sess, idx, "R")), fr.image)
            print(f"captured pair {idx + 1}/{n_frames}")
            idx += 1
    finally:
        left.stop()
        right.stop()
    meta.n_frames = idx
    meta.save(sess / "meta.json")
    return meta
