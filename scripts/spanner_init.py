#!/usr/bin/env python3
"""Create Spanner instance/database and apply schema."""

import os
import sys
from google.cloud import spanner

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from memory.spanner_graph import DDL_STATEMENTS, GRAPH_DDL  # noqa: E402


def main():
    project_id = os.getenv("SPANNER_PROJECT_ID", "")
    instance_id = os.getenv("SPANNER_INSTANCE_ID", "")
    database_id = os.getenv("SPANNER_DATABASE_ID", "")
    instance_config = os.getenv("SPANNER_INSTANCE_CONFIG", "regional-us-central1")

    if not (project_id and instance_id and database_id):
        raise SystemExit("SPANNER_PROJECT_ID/INSTANCE_ID/DATABASE_ID must be set")

    client = spanner.Client(project=project_id)
    instance = client.instance(instance_id)

    if not instance.exists():
        op = instance.create(instance_config=instance_config, node_count=1)
        op.result(timeout=600)

    database = instance.database(database_id)
    if not database.exists():
        op = database.create()
        op.result(timeout=600)

    op = database.update_ddl(DDL_STATEMENTS)
    op.result(timeout=600)
    try:
        op = database.update_ddl([GRAPH_DDL])
        op.result(timeout=600)
    except Exception:
        pass

    print("Spanner schema initialized.")


if __name__ == "__main__":
    main()
