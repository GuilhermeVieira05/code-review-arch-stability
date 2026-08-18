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
        resp = requests.get(url, params=params, headers=_headers(), timeout=30)
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

def count_merged_prs_in_quarter(repo_full_name: str, year: int, q: int) -> int:
    """Fast eligibility check — counts merged PRs without fetching reviews."""
    start, end = quarter_dates(year, q)
    count = 0
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
        count += 1
    return count

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

FIXED_REPOS = {
    "Python": ["django/django", "pallets/flask", "psf/requests"],
    "Java":   ["spring-projects/spring-boot", "elastic/elasticsearch", "square/okhttp"],
}

def collect_all():
    from db import get_connection, init_db
    from config import YEARS_BACK

    now = datetime.now()

    with get_connection() as conn:
        init_db(conn)

        for lang, repo_names in FIXED_REPOS.items():
            print(f"\n=== Collecting {lang} repositories ===", flush=True)

            for name in repo_names:
                repo_meta = _get(f"https://api.github.com/repos/{name}")
                repo_id = str(repo_meta["id"])

                print(f"  {name} (⭐{repo_meta['stargazers_count']:,})", flush=True)
                conn.execute(
                    "INSERT OR IGNORE INTO repos VALUES (?,?,?,?,?,?)",
                    (repo_id, name, lang, repo_meta["stargazers_count"],
                     repo_meta["created_at"], repo_meta["clone_url"])
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
                        print(f"    {quarter_str}: already collected, skipping", flush=True)
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
                    conn.commit()
                    print(f"    {quarter_str}: {len(prs)} PRs, ratio={calculate_review_ratio(prs):.2f}", flush=True)

        conn.commit()

if __name__ == "__main__":
    collect_all()
