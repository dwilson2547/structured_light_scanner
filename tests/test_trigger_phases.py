from sls.capture.trigger import PATTERN_PHASES, phase_of


def test_ab0_cycle():
    assert [phase_of(i, "AB0") for i in range(6)] == ["A", "B", "dark", "A", "B", "dark"]


def test_patterns_cover_protocol():
    assert set(PATTERN_PHASES) == {"AB0", "A0", "ON", "OFF"}


def test_firmware_tables_match_python():
    # keep firmware/trigger_pico/main.py PATTERNS in lockstep with PATTERN_PHASES
    fw = {
        "AB0": ((1, 0), (0, 1), (0, 0)),
        "A0": ((1, 0), (0, 0)),
        "ON": ((1, 1),),
        "OFF": ((0, 0),),
    }
    name = {(1, 0): "A", (0, 1): "B", (1, 1): "AB", (0, 0): "dark"}
    for pat, states in fw.items():
        assert tuple(name[s] for s in states) == PATTERN_PHASES[pat]
