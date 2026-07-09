"""Single UVC camera: V4L2 via OpenCV with a background grab thread.

The OV9281 USB modules present as standard UVC devices. In external-trigger
mode the camera only produces frames when the Pico pulses FSIN, so reads
block until a trigger arrives — the grab thread keeps a small queue so the
consumer never stalls the USB pipe.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray  # 8-bit mono, HxW
    index: int         # per-camera monotonically increasing grab counter
    t_host: float      # host wall-clock at grab return (rough; pairing uses index)


class Camera:
    def __init__(self, device: int | str, width: int = 1280, height: int = 800, fps: int = 100):
        if isinstance(device, str) and device.isdigit():
            device = int(device)  # bare index passed as a string, e.g. from argparse
        self.device = device
        self._cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open {device}")
        # These modules only hit 100+ fps in MJPG (compressed); raw YUYV/GREY caps at
        # 10 fps at 1280x800 and two cameras' worth of raw YUYV saturates a shared
        # USB 2.0 Hi-Speed bus's isochronous budget, causing one stream to lag.
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 4)
        self._queue: queue.Queue[Frame] = queue.Queue(maxsize=256)
        self._running = False
        self._thread: threading.Thread | None = None
        self._count = 0

    @property
    def size(self) -> tuple[int, int]:
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            ok, img = self._cap.read()
            if not ok:
                time.sleep(0.001)
                continue
            if img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            frame = Frame(image=img, index=self._count, t_host=time.monotonic())
            self._count += 1
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                # consumer is behind; drop oldest to stay live
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                self._queue.put_nowait(frame)

    def read(self, timeout: float = 1.0) -> Frame | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        """Drop queued frames and reset the grab counter (call before a triggered run)."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._count = 0

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._cap.release()
