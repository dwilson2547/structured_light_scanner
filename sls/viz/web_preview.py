"""Live two-camera preview served as MJPEG over HTTP.

For field use where there's no monitor to plug into the NUC: point a phone or
tablet browser on the same network at this instead of the cv2.imshow preview.
"""

from __future__ import annotations

import cv2
import numpy as np
from flask import Flask, Response

from ..capture.camera import Camera

_PAGE = """<!doctype html>
<html><head><title>sls preview</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{margin:0;background:#111;display:flex;justify-content:center}
img{max-width:100%;height:auto}</style></head>
<body><img src="/stream"></body></html>
"""


def _mjpeg_frames(left: Camera, right: Camera, scale: float):
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
        combined = np.hstack(tiles)
        ok, jpg = cv2.imencode(".jpg", combined, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")


def serve(left: Camera, right: Camera, host: str = "0.0.0.0", port: int = 8080,
          scale: float = 0.5) -> None:
    left.start()
    right.start()
    app = Flask(__name__)

    @app.route("/")
    def index():
        return _PAGE

    @app.route("/stream")
    def stream():
        return Response(_mjpeg_frames(left, right, scale),
                         mimetype="multipart/x-mixed-replace; boundary=frame")

    try:
        app.run(host=host, port=port, threaded=True, debug=False)
    finally:
        left.stop()
        right.stop()
