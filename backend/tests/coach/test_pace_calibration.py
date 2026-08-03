from dataclasses import dataclass

from app.application.history.pace_calibration_analyzer import (
    PaceCalibrationAnalyzer,
    calibration_directive,
)


@dataclass
class _Block:
    kind: str
    pace_max: str | None
    executed_pace: float | None  # min/km


def test_deltas_only_from_interval_blocks():

    blocks = [
        _Block("warmup", None, 6.5),               # sem alvo -> ignora
        _Block("interval", "5:00", 5.2),           # 312s exec vs 300 alvo -> +12
        _Block("recovery", None, 7.0),             # não é qualidade -> ignora
        _Block("interval", "5:00", 5.1),           # 306 vs 300 -> +6
    ]

    deltas = PaceCalibrationAnalyzer.deltas_from_blocks(blocks)

    assert deltas == [12.0, 6.0]


def test_assess_flags_systematic_slower():

    v = PaceCalibrationAnalyzer.assess([10, 12, 9, 11, 13])

    assert v.adjust is True
    assert v.bias_sec > 0
    d = calibration_directive(v)
    assert "MAIS DEVAGAR" in d
    assert "sustenta" in d


def test_assess_flags_systematic_faster():

    v = PaceCalibrationAnalyzer.assess([-8, -10, -7, -9])

    assert v.adjust is True
    assert v.bias_sec < 0
    assert "MAIS RÁPIDO" in calibration_directive(v)


def test_small_bias_is_noise():

    v = PaceCalibrationAnalyzer.assess([1, -2, 3, 0, 2])

    assert v.adjust is False
    assert calibration_directive(v) == ""


def test_too_few_samples_no_verdict():

    v = PaceCalibrationAnalyzer.assess([15, 20])

    assert v.adjust is False


def test_pace_parse_handles_bad_input():

    blocks = [_Block("interval", "abc", 5.0), _Block("interval", None, 5.0)]

    assert PaceCalibrationAnalyzer.deltas_from_blocks(blocks) == []
