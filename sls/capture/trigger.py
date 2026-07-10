"""Serial control of the Pico trigger/strobe firmware.

Line protocol (newline-terminated ASCII, firmware echoes `ok`/`err ...`):

    START <fps> <pattern>   begin FSIN pulses; pattern: AB0 | A0 | ON | OFF
    STOP                    stop pulsing
    LASER <A|B> <0|1>       manual laser override while stopped
    SYNC [n]                measure L/R strobe-output skew over n frames
    PING                    liveness check

Patterns:
    AB0  3-phase strobe: laser A / laser B / dark      (default scanning mode)
    A0   2-phase: laser A / dark                        (single-line experiments)
    ON   both lasers on every frame                     (alignment/aiming)
    OFF  lasers off, trigger only                       (calibration capture)
"""

from __future__ import annotations

import serial

PATTERNS = ("AB0", "A0", "ON", "OFF")

# frames per strobe cycle for each pattern; frame index % len -> phase
PATTERN_PHASES: dict[str, tuple[str, ...]] = {
    "AB0": ("A", "B", "dark"),
    "A0": ("A", "dark"),
    "ON": ("AB",),
    "OFF": ("dark",),
}


class TriggerBox:
    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 115200, timeout: float = 1.0):
        self._ser = serial.Serial(port, baud, timeout=timeout)

    def _cmd(self, line: str) -> str:
        self._ser.reset_input_buffer()
        self._ser.write((line + "\n").encode())
        resp = self._ser.readline().decode(errors="replace").strip()
        if not resp.startswith("ok"):
            raise RuntimeError(f"trigger box: {line!r} -> {resp!r}")
        return resp

    def ping(self) -> None:
        self._cmd("PING")

    def start(self, fps: int, pattern: str = "AB0") -> None:
        if pattern not in PATTERNS:
            raise ValueError(f"pattern must be one of {PATTERNS}")
        self._cmd(f"START {fps} {pattern}")

    def stop(self) -> None:
        self._cmd("STOP")

    def laser(self, which: str, on: bool) -> None:
        self._cmd(f"LASER {which} {1 if on else 0}")

    def sync(self, frames: int = 32) -> str:
        """Measure camera strobe timing; blocks ~30 ms per frame on the Pico."""
        old_timeout = self._ser.timeout
        self._ser.timeout = frames * 0.05 + 5.0
        try:
            return self._cmd(f"SYNC {frames}")
        finally:
            self._ser.timeout = old_timeout

    def close(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
        self._ser.close()

    def __enter__(self) -> "TriggerBox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def phase_of(frame_index: int, pattern: str) -> str:
    """Which strobe phase a frame belongs to: 'A', 'B', 'AB', or 'dark'.

    Valid because capture starts from a flushed queue after START, so camera
    grab counters align with the firmware's frame counter.
    """
    phases = PATTERN_PHASES[pattern]
    return phases[frame_index % len(phases)]
