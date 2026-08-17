import pytest
from analyze import aggregate_instability, quarter_to_date

def test_quarter_to_date_q1():
    assert quarter_to_date("2024-Q1") == "2024-03-31"

def test_quarter_to_date_q4():
    assert quarter_to_date("2023-Q4") == "2023-12-31"

def test_aggregate_instability_basic():
    packages = [
        {"package": "a", "ce": 2, "ca": 0},
        {"package": "b", "ce": 0, "ca": 2},
    ]
    result = aggregate_instability(packages)
    # a: I=1.0, b: I=0.0, weighted avg of ce/ca: ce_avg=1, ca_avg=1 → I=0.5
    assert result["instability"] == pytest.approx(0.5)
    assert result["ce"] == pytest.approx(1.0)
    assert result["ca"] == pytest.approx(1.0)

def test_aggregate_instability_all_isolated():
    # packages with ce=0 and ca=0 are excluded from aggregation
    assert aggregate_instability([{"package": "a", "ce": 0, "ca": 0}]) is None

def test_aggregate_instability_empty():
    assert aggregate_instability([]) is None
