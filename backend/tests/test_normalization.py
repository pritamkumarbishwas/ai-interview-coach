"""Phase 6: cross-candidate normalization (advisory, cohort-relative)."""


from app.services.normalization_service import normalize


def test_percentiles_rank_a_cohort() -> None:
    results = normalize([90.0, 40.0, 70.0, 40.0])

    # 90 is strictly highest -> top of the cohort.
    assert results[0].percentile == 87.5
    # The two 40s tie; their shared mean-rank percentile is (0 + 0.5*2) / 4 -> 25.
    assert results[1].percentile == 25.0
    assert results[3].percentile == 25.0
    assert results[2].percentile == 62.5


def test_z_scores_are_signed_and_zero_without_spread() -> None:
    results = normalize([60.0, 80.0, 100.0])
    assert [item.z_score for item in results] == [-1.22, 0.0, 1.22]
    # Identical cohort -> no spread, so z is 0 rather than a division by zero.
    assert [item.z_score for item in normalize([55.0, 55.0])] == [0.0, 0.0]


def test_single_candidate_is_not_presented_as_top_of_cohort() -> None:
    (only,) = normalize([88.0])
    assert only.percentile == 50.0
    assert only.z_score == 0.0


def test_empty_cohort_returns_nothing() -> None:
    assert normalize([]) == []


def test_order_is_preserved() -> None:
    scores = [10.0, 20.0, 30.0]
    assert [item.value for item in normalize(scores)] == scores


def test_percentile_is_monotonic_in_score() -> None:
    scores = [12.0, 55.0, 55.5, 91.0]
    percentiles = [item.percentile for item in normalize(scores)]
    assert percentiles == sorted(percentiles)
