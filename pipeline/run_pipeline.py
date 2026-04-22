"""Orchestrate the full retrain pipeline: scrape → migrate → train → upload.

Run manually or via GitHub Actions on a cron schedule.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    """Run a subprocess and raise on failure."""
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full retrain pipeline")
    parser.add_argument("--items", type=int, default=5000, help="Number of listings to scrape")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip the scraping step")
    args = parser.parse_args()

    # 1. Scrape new data
    if not args.skip_scrape:
        log.info("=== Step 1: Scraping listings ===")
        run([PYTHON, "ml_scraper/scraper.py", "--items", str(args.items)])
    else:
        log.info("=== Step 1: Skipped scraping ===")

    # 2. Migrate CSV to SQLite
    log.info("=== Step 2: Migrating data to SQLite ===")
    run([PYTHON, "db/migrate.py"])

    # 3. Train model
    log.info("=== Step 3: Training model ===")
    run([PYTHON, "ml_model/train.py"])

    log.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
