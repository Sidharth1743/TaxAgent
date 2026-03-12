#!/usr/bin/env python3
"""Apply Spanner schema DDL to an existing instance/database.

The instance and database are created by scripts/gcp_setup.sh.
This script only applies (or updates) the table and graph schema.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from config import (  # noqa: E402
    SPANNER_DATABASE_ID,
    SPANNER_INSTANCE_ID,
    SPANNER_PROJECT_ID,
)

from google.cloud import spanner  # noqa: E402

from memory.spanner_graph import DDL_STATEMENTS, GRAPH_DDL  # noqa: E402


def main():
    if not (SPANNER_PROJECT_ID and SPANNER_INSTANCE_ID and SPANNER_DATABASE_ID):
        raise SystemExit(
            "SPANNER_PROJECT_ID/INSTANCE_ID/DATABASE_ID must be set "
            "(check .env or run scripts/gcp_setup.sh first)"
        )

    client = spanner.Client(project=SPANNER_PROJECT_ID)
    instance = client.instance(SPANNER_INSTANCE_ID)

    if not instance.exists():
        raise SystemExit(
            f"Spanner instance '{SPANNER_INSTANCE_ID}' does not exist. "
            "Run scripts/gcp_setup.sh first to provision it."
        )

    database = instance.database(SPANNER_DATABASE_ID)
    if not database.exists():
        raise SystemExit(
            f"Spanner database '{SPANNER_DATABASE_ID}' does not exist. "
            "Run scripts/gcp_setup.sh first to provision it."
        )

    print(f"Applying schema to {SPANNER_INSTANCE_ID}/{SPANNER_DATABASE_ID}...")

    op = database.update_ddl(DDL_STATEMENTS)
    op.result(timeout=600)
    print("  Table DDL applied.")

    try:
        op = database.update_ddl([GRAPH_DDL])
        op.result(timeout=600)
        print("  Graph DDL applied.")
    except Exception:
        print("  Graph DDL skipped (may already exist or not supported).")

    print("Spanner schema initialized.")


if __name__ == "__main__":
    main()
