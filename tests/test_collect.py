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

from collect import fetch_prs_in_quarter, fetch_commits_in_quarter

def test_fetch_prs_marks_reviewed_by_third_party(mocker):
    mocker.patch("collect._get", side_effect=[
        # page 1: one merged PR
        [{"number": 1, "user": {"login": "alice"}, "merged_at": "2024-02-10T12:00:00Z"}],
        # page 2: empty (pagination end for PRs)
        [],
        # reviews for PR #1: approved by bob (not alice)
        [{"state": "APPROVED", "user": {"login": "bob"}}],
        # empty page (pagination end for reviews)
        [],
    ])
    prs = fetch_prs_in_quarter("owner/repo", 2024, 1)
    assert len(prs) == 1
    assert prs[0]["reviewed_by_third_party"] is True

def test_fetch_prs_self_review_not_counted(mocker):
    mocker.patch("collect._get", side_effect=[
        [{"number": 2, "user": {"login": "alice"}, "merged_at": "2024-02-10T12:00:00Z"}],
        [],
        [{"state": "APPROVED", "user": {"login": "alice"}}],
        [],
    ])
    prs = fetch_prs_in_quarter("owner/repo", 2024, 1)
    assert prs[0]["reviewed_by_third_party"] is False

def test_fetch_commits_excludes_bots(mocker):
    mocker.patch("collect._get", side_effect=[
        [
            {"author": {"login": "alice"}},
            {"author": {"login": "github-actions[bot]"}},
        ],
        [],
    ])
    authors = fetch_commits_in_quarter("owner/repo", 2024, 1)
    assert authors == ["alice"]
