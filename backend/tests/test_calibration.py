"""Phase 6: deterministic calibration metrics against a human-scored golden set."""

from app.services.calibration_service import CalibrationRow, evaluate


def test_metrics_on_a_golden_set() -> None:
    rows = [
        CalibrationRow("a", ai_score=80.0, human_score=75.0),  # +5
        CalibrationRow("b", ai_score=60.0, human_score=70.0),  # -10
        CalibrationRow("c", ai_score=50.0, human_score=45.0),  # +5
        CalibrationRow("d", ai_score=90.0, human_score=60.0),  # +30 (worst)
    ]
    report = evaluate(rows, tolerance=10.0)

    assert report.samples == 4
    assert report.tolerance == 10.0
    assert report.mean_absolute_error == 12.5  # (5 + 10 + 5 + 30) / 4
    assert report.mean_signed_bias == 7.5  # (5 - 10 + 5 + 30) / 4 -> lenient
    assert report.max_absolute_error == 30.0
    assert report.agreement_rate == 0.75  # 3 of 4 within tolerance
    assert report.worst_case == "d"


def test_empty_set_is_neutral() -> None:
    report = evaluate([])
    assert report.samples == 0
    assert report.mean_absolute_error == 0.0
    assert report.mean_signed_bias == 0.0
    assert report.agreement_rate == 0.0
    assert report.worst_case == ""


def test_custom_tolerance_widens_agreement() -> None:
    rows = [CalibrationRow("a", ai_score=100.0, human_score=80.0)]
    assert evaluate(rows, tolerance=10.0).agreement_rate == 0.0
    assert evaluate(rows, tolerance=20.0).agreement_rate == 1.0
