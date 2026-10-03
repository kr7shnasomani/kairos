"""
Shift the showcase plant forward so it always reads as recent (`scripts/showcase/redate.py`).

Moves only the rows the showcase loader wrote (found by their deterministic ids), by a whole number of
days, so the newest event lands on yesterday. Updates time columns only; creates and deletes nothing.
A same-day re-run shifts by zero. Dry run by default.

    python scripts/redate_showcase.py            # dry run: prints the shift and the row counts
    python scripts/redate_showcase.py --apply    # writes (the current stores)

With SHOWCASE_AUTO_REDATE=true the API runs the same thing about once a day by itself.
"""

import argparse
import sys

sys.path.insert(0, "/app")

import structlog
from neo4j import GraphDatabase
from supabase import create_client

from api.config import Settings
from scripts.showcase import files
from scripts.showcase.redate import redate

log = structlog.get_logger(__name__)


def run(settings: Settings, *, apply: bool) -> dict:
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    sc = files.read(files.showcase_root()).showcase  # only its ids are used: they do not depend on the user or the date
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    try:
        return redate(sb, driver, sc, apply=apply)
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-date the showcase plant.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    summary = run(Settings(), apply=args.apply)
    print(summary)
    if not args.apply:
        print("Dry run: nothing was written. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
