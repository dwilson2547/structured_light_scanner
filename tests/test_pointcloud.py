import numpy as np

from sls.process.pointcloud import CloudAccumulator, read_ply, write_ply
from sls.process.register import TurntableRegistration


def test_ply_roundtrip(tmp_path):
    pts = np.random.default_rng(1).normal(size=(100, 3)).astype(np.float32)
    p = tmp_path / "out.ply"
    write_ply(p, pts)
    assert np.array_equal(read_ply(p), pts)


def test_accumulator_applies_pose():
    acc = CloudAccumulator()
    pose = np.eye(4)
    pose[:3, 3] = [1, 2, 3]
    acc.add(np.zeros((2, 3), np.float32), pose=pose)
    assert np.allclose(acc.points(), [[1, 2, 3], [1, 2, 3]])


def test_turntable_full_revolution_is_identity():
    reg = TurntableRegistration(
        axis_point=[0.0, 0.1, 0.35], axis_dir=[0, 1, 0], deg_per_cycle=10.0)
    assert np.allclose(reg.pose(36), np.eye(4), atol=1e-12)
    # a point on the axis never moves
    p = np.array([0.0, 0.1, 0.35, 1.0])
    assert np.allclose(reg.pose(7) @ p, p)
