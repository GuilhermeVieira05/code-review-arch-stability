import os

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPOS_PER_LANGUAGE = 3
YEARS_BACK = 2
MIN_STARS = 500
MIN_PRS_PER_QUARTER = 10
MIN_REVIEW_RATIO_THRESHOLD = 0.5
LANGUAGES = ["Python", "Java"]
DATA_DIR = "data"
SNAPSHOTS_DIR = "data/snapshots"
DB_PATH = "data/mvp.db"
