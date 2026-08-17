import requests
import time
import math
from collections import Counter
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
        if len(items) < 100:
            break
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
