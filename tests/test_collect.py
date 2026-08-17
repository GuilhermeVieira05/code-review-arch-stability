import math
import pytest
from collect import quarter_dates, calculate_review_ratio, calculate_author_entropy

def test_quarter_dates_q1():
    start, end = quarter_dates(2024, 1)
    assert start == "2024-01-01"
    assert end == "2024-03-31"

def test_quarter_dates_q4():
    start, end = quarter_dates(2023, 4)
    assert start == "2023-10-01"
    assert end == "2023-12-31"

def test_review_ratio_all_reviewed():
    prs = [{"reviewed_by_third_party": True}, {"reviewed_by_third_party": True}]
    assert calculate_review_ratio(prs) == 1.0

def test_review_ratio_none_reviewed():
    prs = [{"reviewed_by_third_party": False}]
    assert calculate_review_ratio(prs) == 0.0

def test_review_ratio_empty():
    assert calculate_review_ratio([]) == 0.0

def test_author_entropy_single_author():
    result = calculate_author_entropy(["alice", "alice", "alice"])
    assert result == pytest.approx(0.0)

def test_author_entropy_two_equal_authors():
    result = calculate_author_entropy(["alice", "bob"])
    assert result == pytest.approx(1.0)
