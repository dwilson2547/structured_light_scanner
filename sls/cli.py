"""`sls` command line: preview | board | capture | calibrate | scan | process."""

from __future__ import annotations

import argparse
from pathlib import Path

SESSIONS = Path("sessions")


def _cam_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--left", type=int, default=0, help="left camera /dev/video index")
    p.add_argument("--right", type=int, default=2, help="right camera /dev/video index")


def cmd_preview(args) -> None:
    from .capture.camera import Camera
    from .viz.preview import preview

    preview(Camera(args.left), Camera(args.right))


def cmd_board(args) -> None:
    from .calib.intrinsics import export_board_png, make_board

    out = Path(args.out)
    export_board_png(out, make_board())
    print(f"wrote {out} — print at 100% scale, glue to something rigid,")
    print("then measure a square and pass --square-mm to calibrate if it isn't 30.0")


def cmd_capture(args) -> None:
    from .capture.camera import Camera
    from .capture.session import run_free, run_triggered

    left, right = Camera(args.left), Camera(args.right)
    if args.free:
        meta = run_free(SESSIONS, args.session, left, right,
                        n_frames=args.frames, interval_s=args.interval)
    else:
        from .capture.trigger import TriggerBox

        with TriggerBox(args.port) as trig:
            meta = run_triggered(SESSIONS, args.session, left, right, trig,
                                 fps=args.fps, pattern="OFF", duration_s=args.duration)
    print(f"session {meta.name}: {meta.n_frames} pairs, {len(meta.dropped)} dropped")


def cmd_calibrate(args) -> None:
    import cv2

    from .calib.intrinsics import calibrate_intrinsics, make_board
    from .calib.stereo import calibrate_stereo
    from .capture.session import SessionMeta, frame_path

    sess = SESSIONS / args.session
    meta = SessionMeta.load(sess / "meta.json")
    imgs_l = [cv2.imread(str(frame_path(sess, i, "L")), cv2.IMREAD_GRAYSCALE)
              for i in range(meta.n_frames)]
    imgs_r = [cv2.imread(str(frame_path(sess, i, "R")), cv2.IMREAD_GRAYSCALE)
              for i in range(meta.n_frames)]
    board = make_board(square_mm=args.square_mm,
                       marker_mm=args.square_mm * 22.0 / 30.0)

    K_l, dist_l, rms_l, used_l = calibrate_intrinsics(imgs_l, board)
    K_r, dist_r, rms_r, used_r = calibrate_intrinsics(imgs_r, board)
    print(f"intrinsics L: rms {rms_l:.3f} px on {len(used_l)} views")
    print(f"intrinsics R: rms {rms_r:.3f} px on {len(used_r)} views")

    bundle = calibrate_stereo(imgs_l, imgs_r, board, K_l, dist_l, K_r, dist_r)
    bundle.save(Path(args.out))
    import numpy as np

    print(f"stereo: rms {bundle.rms_stereo:.3f} px, "
          f"baseline {np.linalg.norm(bundle.T) * 1000:.1f} mm -> {args.out}.npz")
    if bundle.rms_stereo > 0.5:
        print("WARNING: stereo rms > 0.5 px — recapture with more varied board poses")


def cmd_scan(args) -> None:
    from .capture.camera import Camera
    from .capture.session import run_triggered
    from .capture.trigger import TriggerBox

    left, right = Camera(args.left), Camera(args.right)
    with TriggerBox(args.port) as trig:
        meta = run_triggered(SESSIONS, args.session, left, right, trig,
                             fps=args.fps, pattern=args.pattern,
                             duration_s=args.duration)
    print(f"scan {meta.name}: {meta.n_frames} pairs, {len(meta.dropped)} dropped")


def cmd_process(args) -> None:
    from .calib.stereo import CalibBundle
    from .process.pipeline import process_session
    from .process.pointcloud import write_ply

    calib = CalibBundle.load(Path(args.calib))
    pts = process_session(SESSIONS / args.session, calib,
                          z_near=args.z_near, z_far=args.z_far)
    write_ply(Path(args.out), pts)
    print(f"{len(pts)} points -> {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="sls")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preview", help="live two-camera view (free-running)")
    _cam_args(p)
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("board", help="export the ChArUco calibration board PNG")
    p.add_argument("--out", default="charuco_board.png")
    p.set_defaults(fn=cmd_board)

    p = sub.add_parser("capture", help="capture a calibration session")
    _cam_args(p)
    p.add_argument("--session", required=True)
    p.add_argument("--free", action="store_true", help="free-running (no trigger box)")
    p.add_argument("--frames", type=int, default=40)
    p.add_argument("--interval", type=float, default=1.0, help="s between pairs (free mode)")
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--duration", type=float, default=40.0)
    p.set_defaults(fn=cmd_capture)

    p = sub.add_parser("calibrate", help="intrinsics + stereo from a session")
    p.add_argument("--session", required=True)
    p.add_argument("--out", required=True, help="bundle stem, e.g. calib/rig01")
    p.add_argument("--square-mm", type=float, default=30.0)
    p.set_defaults(fn=cmd_calibrate)

    p = sub.add_parser("scan", help="triggered strobed capture")
    _cam_args(p)
    p.add_argument("--session", required=True)
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--fps", type=int, default=100)
    p.add_argument("--pattern", default="AB0", choices=["AB0", "A0"])
    p.add_argument("--duration", type=float, default=10.0)
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("process", help="session + calib -> PLY")
    p.add_argument("--session", required=True)
    p.add_argument("--calib", required=True, help="bundle stem from calibrate")
    p.add_argument("--out", required=True)
    p.add_argument("--z-near", type=float, default=0.20)
    p.add_argument("--z-far", type=float, default=0.60)
    p.set_defaults(fn=cmd_process)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
