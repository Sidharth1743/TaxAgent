#!/usr/bin/env python3
"""Verify GCP resources (Spanner and Document AI) are working.

Run after scripts/gcp_setup.sh to confirm provisioned resources are accessible.
Exit 0 if all checks pass (or Document AI is skipped), exit 1 on failure.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from config import (  # noqa: E402
    DOCAI_LOCATION,
    DOCAI_PROCESSOR_ID,
    SPANNER_DATABASE_ID,
    SPANNER_INSTANCE_ID,
    SPANNER_PROJECT_ID,
)


def verify_spanner() -> bool:
    """Test Spanner connectivity: ensure schema, write, and read back."""
    from google.cloud import spanner

    from memory.spanner_graph import ensure_schema, upsert_basic_user_session

    if not (SPANNER_PROJECT_ID and SPANNER_INSTANCE_ID and SPANNER_DATABASE_ID):
        print("[SPANNER] FAIL -- Spanner config not set in .env / config.py")
        return False

    try:
        client = spanner.Client(project=SPANNER_PROJECT_ID)
        instance = client.instance(SPANNER_INSTANCE_ID)
        database = instance.database(SPANNER_DATABASE_ID)

        # Apply schema (idempotent)
        print("[SPANNER] Applying schema...")
        ensure_schema(database)

        # Write test user + session
        print("[SPANNER] Writing test user/session...")
        upsert_basic_user_session(database, "test-user", "test-session")

        # Read back
        print("[SPANNER] Reading back test user...")
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(
                "SELECT user_id FROM Users WHERE user_id = 'test-user'"
            )
            rows = list(results)

        if rows and rows[0][0] == "test-user":
            print("[SPANNER] PASS")
            return True
        else:
            print("[SPANNER] FAIL -- test-user not found after write")
            return False
    except Exception as exc:
        print(f"[SPANNER] FAIL -- {exc}")
        return False


def verify_docai() -> bool:
    """Test Document AI processor with a minimal inline document."""
    if not DOCAI_PROCESSOR_ID:
        print(
            "[DOCAI] SKIP -- Set DOCAI_PROCESSOR_ID in .env after running gcp_setup.sh"
        )
        return True  # Skip counts as pass

    try:
        from google.cloud import documentai

        client = documentai.DocumentProcessorServiceClient(
            client_options={
                "api_endpoint": f"{DOCAI_LOCATION}-documentai.googleapis.com"
            }
        )

        processor_name = client.processor_path(
            SPANNER_PROJECT_ID, DOCAI_LOCATION, DOCAI_PROCESSOR_ID
        )

        # Minimal raw text document for testing
        raw_document = documentai.RawDocument(
            content=b"Name: Test User\nSSN: 000-00-0000\nWages: $50,000",
            mime_type="text/plain",
        )

        request = documentai.ProcessRequest(
            name=processor_name,
            raw_document=raw_document,
        )

        result = client.process_document(request=request)
        if result.document and result.document.text:
            print(f"[DOCAI] PASS -- parsed {len(result.document.text)} chars")
            return True
        else:
            print("[DOCAI] FAIL -- empty document response")
            return False
    except Exception as exc:
        print(f"[DOCAI] FAIL -- {exc}")
        return False


def main():
    print("=" * 50)
    print("  GCP Resource Verification")
    print("=" * 50)
    print()

    spanner_ok = verify_spanner()
    print()
    docai_ok = verify_docai()

    print()
    print("=" * 50)
    if spanner_ok and docai_ok:
        print("  All checks passed.")
        sys.exit(0)
    else:
        print("  Some checks FAILED. See output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
