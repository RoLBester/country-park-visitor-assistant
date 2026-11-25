import pytest

from evaluation.run import CASES, exercise
from evaluation.synthetic import simulated


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["group"] != "synthetic"], ids=lambda c: c["id"]
)
def test_labelled_api_case(client, case):
    result = exercise(client, case)
    assert result["passed"], result


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["group"] == "synthetic"], ids=lambda c: c["id"]
)
def test_synthetic_notice(case):
    result = simulated(case)
    assert result.status == case["status"]
    assert set(case["sources"]) <= set(result.source_ids)
    if result.area == "centre":
        assert result.notices == []
    if case["fixture"] == "undated_reopening":
        assert result.notices[0]["from"] is None
        assert "unspecified" in result.message
