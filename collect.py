import requests
import time
import math
from collections import Counter
from datetime import datetime, timedelta
from config import GITHUB_TOKEN

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def _get(url: str, params: dict = None) -> any:
    while True:
        resp = requests.get(url, params=params, headers=_headers())
        if resp.status_code == 403:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", 1))
            if remaining == 0:
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time() + 5, 1)
                print(f"  Rate limit hit, sleeping {wait:.0f}s")
                time.sleep(wait)
                continue
        resp.raise_for_status()
        return resp.json()

def _paginate(url: str, params: dict = None):
    params = dict(params or {})
    params["per_page"] = 100
    page = 1
    while True:
        params["page"] = page
        items = _get(url, params)
        if not items:
            break
        yield from items
        page += 1

def quarter_dates(year: int, q: int) -> tuple[str, str]:
    starts = {1: (1, 1), 2: (4, 1), 3: (7, 1), 4: (10, 1)}
    ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    sm, sd = starts[q]
    em, ed = ends[q]
    return f"{year}-{sm:02d}-{sd:02d}", f"{year}-{em:02d}-{ed:02d}"

def calculate_review_ratio(prs: list[dict]) -> float:
    if not prs:
        return 0.0
    reviewed = sum(1 for pr in prs if pr["reviewed_by_third_party"])
    return reviewed / len(prs)

def calculate_author_entropy(authors: list[str]) -> float:
    if not authors:
        return 0.0
    counts = Counter(authors)
    total = len(authors)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())

def fetch_prs_in_quarter(repo_full_name: str, year: int, q: int) -> list[dict]:
    start, end = quarter_dates(year, q)
    raw_prs = []
    for pr in _paginate(
        f"https://api.github.com/repos/{repo_full_name}/pulls",
        {"state": "closed", "sort": "updated", "direction": "desc"},
    ):
        merged_at = pr.get("merged_at")
        if not merged_at:
            continue
        merged_date = merged_at[:10]
        if merged_date < start:
            continue
        if merged_date > end:
            continue
        raw_prs.append(pr)

    prs = []
    for pr in raw_prs:
        author = pr["user"]["login"]
        reviews = list(_paginate(
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr['number']}/reviews"
        ))
        approved_by_other = any(
            r["state"] == "APPROVED" and r["user"]["login"] != author
            for r in reviews
        )
        prs.append({"number": pr["number"], "reviewed_by_third_party": approved_by_other})
    return prs

def fetch_commits_in_quarter(repo_full_name: str, year: int, q: int) -> list[str]:
    start, end = quarter_dates(year, q)
    authors = []
    for commit in _paginate(
        f"https://api.github.com/repos/{repo_full_name}/commits",
        {"since": f"{start}T00:00:00Z", "until": f"{end}T23:59:59Z"},
    ):
        login = (commit.get("author") or {}).get("login", "")
        if login and "[bot]" not in login:
            authors.append(login)
    return authors

def search_repos(language: str, min_stars: int, created_before: str) -> list[dict]:
    data = _get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"language:{language} stars:>={min_stars} created:<{created_before} fork:false",
            "sort": "stars",
            "order": "desc",
            "per_page": 30,
        },
    )
    return data["items"]

def collect_all():
    from db import get_connection, init_db
    from config import (REPOS_PER_LANGUAGE, MIN_STARS, YEARS_BACK,
                        LANGUAGES, MIN_REVIEW_RATIO_THRESHOLD, MIN_PRS_PER_QUARTER)

    created_before = (datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    now = datetime.now()

    with get_connection() as conn:
        init_db(conn)

        for lang in LANGUAGES:
            print(f"\n=== Selecting {REPOS_PER_LANGUAGE} {lang} repositories ===")
            candidates = search_repos(lang, MIN_STARS, created_before)
            selected = 0

            for repo in candidates:
                if selected >= REPOS_PER_LANGUAGE:
                    break

                repo_id = str(repo["id"])
                name = repo["full_name"]

                # Quick eligibility check on the most recent complete quarter
                sample_q = (now.month - 1) // 3 + 1
                sample_year = now.year
                if sample_q == 1:
                    sample_q, sample_year = 4, now.year - 1
                else:
                    sample_q -= 1

                sample_prs = fetch_prs_in_quarter(name, sample_year, sample_q)
                if len(sample_prs) < MIN_PRS_PER_QUARTER:
                    print(f"  skip {name}: too few PRs ({len(sample_prs)})")
                    continue
                ratio = calculate_review_ratio(sample_prs)
                if ratio < MIN_REVIEW_RATIO_THRESHOLD:
                    print(f"  skip {name}: review ratio too low ({ratio:.2f})")
                    continue

                print(f"  selected: {name}")
                conn.execute(
                    "INSERT OR IGNORE INTO repos VALUES (?,?,?,?,?,?)",
                    (repo_id, name, lang, repo["stargazers_count"],
                     repo["created_at"], repo["clone_url"])
                )

                start_dt = now - timedelta(days=365 * YEARS_BACK)
                for i in range(8):
                    qdate = start_dt + timedelta(days=91 * i)
                    q = (qdate.month - 1) // 3 + 1
                    quarter_str = f"{qdate.year}-Q{q}"

                    exists = conn.execute(
                        "SELECT 1 FROM quarters WHERE repo_id=? AND quarter=?",
                        (repo_id, quarter_str)
                    ).fetchone()
                    if exists:
                        continue

                    prs = fetch_prs_in_quarter(name, qdate.year, q)
                    authors = fetch_commits_in_quarter(name, qdate.year, q)
                    conn.execute(
                        "INSERT OR REPLACE INTO quarters VALUES (?,?,?,?,?,?)",
                        (repo_id, quarter_str,
                         calculate_review_ratio(prs),
                         calculate_author_entropy(authors),
                         len(prs),
                         sum(1 for p in prs if p["reviewed_by_third_party"]))
                    )
                    print(f"    {quarter_str}: {len(prs)} PRs, ratio={calculate_review_ratio(prs):.2f}")

                selected += 1

        conn.commit()

if __name__ == "__main__":
    collect_all()
