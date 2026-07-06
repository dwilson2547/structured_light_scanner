"""Live two-camera preview (free-running; for aiming, focus, and sanity)."""

from __future__ import annotations

import cv2
import numpy as np

from ..capture.camera import Camera


def preview(left: Camera, right: Camera, scale: float = 0.5) -> None:
    left.start()
    right.start()
    print("q quits; f prints measured fps")
    import time

    n, t0 = 0, time.monotonic()
    try:
        while True:
            fl = left.read(timeout=1.0)
            fr = right.read(timeout=1.0)
            tiles = []
            for f, name in ((fl, "L"), (fr, "R")):
                if f is None:
                    tiles.append(np.zeros((int(800 * scale), int(1280 * scale)), np.uint8))
                    continue
                img = cv2.resize(f.image, None, fx=scale, fy=scale)
                cv2.putText(img, f"{name} #{f.index}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 2)
                tiles.append(img)
            n += 1
            cv2.imshow("sls preview", np.hstack(tiles))
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("f"):
                dt = time.monotonic() - t0
                print(f"{n / dt:.1f} pair/s over {dt:.1f}s")
                n, t0 = 0, time.monotonic()
    finally:
        left.stop()
        right.stop()
        cv2.destroyAllWindows()
