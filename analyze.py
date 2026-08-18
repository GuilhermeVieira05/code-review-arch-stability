from __future__ import annotations

import subprocess
import json
import shutil
import sys
import grimp
from pathlib import Path
from db import get_connection
from config import SNAPSHOTS_DIR

JAVA_JAR = "java_analyzer/target/analyzer-1.0-jar-with-dependencies.jar"

def quarter_to_date(quarter: str) -> str:
    year, q = quarter.split("-Q")
    ends = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
    return f"{year}-{ends[q]}"

def aggregate_instability(packages: list[dict]) -> dict | None:
    if not packages:
        return None
    per_module_i = []
    total_ce, total_ca = 0, 0
    for p in packages:
        ce, ca = p["ce"], p["ca"]
        if ce + ca > 0:
            per_module_i.append(ce / (ce + ca))
            total_ce += ce
            total_ca += ca
    if not per_module_i:
        return None
    n = len(per_module_i)
    return {
        "instability": sum(per_module_i) / n,
        "ce": total_ce / n,
        "ca": total_ca / n,
    }

_SKIP_DIRS = {"tests", "test", "docs", "doc", "examples", "scripts", "benchmarks"}

def _find_python_packages(snapshot_dir: Path) -> tuple[list[str], Path]:
    # Prefer src/ or lib/ layout over root layout
    for subdir in ("src", "lib"):
        candidate = snapshot_dir / subdir
        if candidate.is_dir():
            pkgs = [
                d.name for d in candidate.iterdir()
                if d.is_dir() and (d / "__init__.py").exists()
                and d.name not in _SKIP_DIRS
            ]
            if pkgs:
                return pkgs, candidate

    pkgs = [
        d.name for d in snapshot_dir.iterdir()
        if d.is_dir() and (d / "__init__.py").exists()
        and d.name not in _SKIP_DIRS
    ]
    return pkgs, snapshot_dir

def calculate_python_instability(snapshot_dir: Path) -> dict | None:
    packages, pkg_root = _find_python_packages(snapshot_dir)
    if not packages:
        return None
    old_path = sys.path[:]
    try:
        if str(pkg_root) not in sys.path:
            sys.path.insert(0, str(pkg_root))
        graph = grimp.build_graph(*packages)
    except Exception:
        return None
    finally:
        sys.path = old_path

    pkg_data = []
    for module in graph.modules:
        ce = len(graph.find_modules_directly_imported_by(module))
        ca = len(graph.find_modules_that_directly_import(module))
        pkg_data.append({"package": module, "ce": ce, "ca": ca})

    result = aggregate_instability(pkg_data)
    if result:
        result["num_files"] = len(list(snapshot_dir.rglob("*.py")))
    return result

def calculate_java_instability(snapshot_dir: Path) -> dict | None:
    try:
        proc = subprocess.run(
            ["java", "-jar", JAVA_JAR, str(snapshot_dir)],
            capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        packages = json.loads(proc.stdout.strip())
    except Exception:
        return None

    result = aggregate_instability(packages)
    if result:
        result["num_files"] = len(list(snapshot_dir.rglob("*.java")))
    return result

def _get_commit_at_date(repo_dir: Path, date_str: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-list", "-1",
         f"--before={date_str}T23:59:59", "HEAD"],
        capture_output=True, text=True
    )
    sha = result.stdout.strip()
    return sha if sha else None

def _checkout_snapshot(repo_dir: Path, commit_sha: str, snapshot_dir: Path):
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", str(repo_dir), "archive", commit_sha],
        check=True, capture_output=True
    )
    subprocess.run(
        ["tar", "-x", "-C", str(snapshot_dir)],
        input=archive.stdout, check=True
    )

def analyze_all():
    with get_connection() as conn:
        repos = conn.execute(
            "SELECT id, name, language, clone_url FROM repos"
        ).fetchall()

        for repo_id, name, language, clone_url in repos:
            print(f"\n=== Analyzing {name} ({language}) ===")
            repo_dir = Path(SNAPSHOTS_DIR) / f"_clone_{repo_id}"

            if not repo_dir.exists():
                print(f"  Cloning {clone_url}...")
                subprocess.run(
                    ["git", "clone", "--filter=blob:none", "--no-single-branch",
                     clone_url, str(repo_dir)],
                    check=True, capture_output=True
                )

            quarters = conn.execute(
                "SELECT quarter FROM quarters WHERE repo_id=?", (repo_id,)
            ).fetchall()

            for (quarter,) in quarters:
                done = conn.execute(
                    "SELECT status FROM snapshots WHERE repo_id=? AND quarter=?",
                    (repo_id, quarter)
                ).fetchone()
                if done:
                    print(f"  {quarter}: already {done[0]}, skipping")
                    continue

                end_date = quarter_to_date(quarter)
                commit_sha = _get_commit_at_date(repo_dir, end_date)
                if not commit_sha:
                    conn.execute(
                        "INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                        (repo_id, quarter, "failed")
                    )
                    print(f"  {quarter}: no commit found")
                    continue

                snapshot_dir = Path(SNAPSHOTS_DIR) / f"{repo_id}_{quarter}"
                try:
                    _checkout_snapshot(repo_dir, commit_sha, snapshot_dir)

                    result = (
                        calculate_python_instability(snapshot_dir)
                        if language == "Python"
                        else calculate_java_instability(snapshot_dir)
                    )

                    if result:
                        conn.execute(
                            "INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?)",
                            (repo_id, quarter, result["instability"],
                             result["ce"], result["ca"], result.get("num_files", 0))
                        )
                        conn.execute(
                            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                            (repo_id, quarter, "done")
                        )
                        conn.commit()
                        print(f"  {quarter}: I={result['instability']:.3f}")
                    else:
                        conn.execute(
                            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                            (repo_id, quarter, "failed")
                        )
                        conn.commit()
                        print(f"  {quarter}: analysis failed")
                except Exception as e:
                    conn.execute(
                        "INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                        (repo_id, quarter, "failed")
                    )
                    conn.commit()
                    print(f"  {quarter}: error — {e}")
                finally:
                    shutil.rmtree(snapshot_dir, ignore_errors=True)

        conn.commit()

if __name__ == "__main__":
    analyze_all()
