#!/usr/bin/env bash
# GCP provisioning script for TaxAgent.
# Creates Spanner free-trial instance, database, and Document AI processor.
# Idempotent -- safe to re-run.

set -euo pipefail

PROJECT_ID="newproject-489516"
SPANNER_INSTANCE="taxclarity-free"
SPANNER_DB="taxclarity"
SPANNER_CONFIG="regional-us-central1"
DOCAI_LOCATION="us"
DOCAI_PROCESSOR_NAME="taxclarity-w2-parser"
DOCAI_PROCESSOR_TYPE="FORM_PARSER_PROCESSOR"

# ---------------------------------------------------------------------------
# 1. Pre-flight checks
# ---------------------------------------------------------------------------
echo "==> Pre-flight checks"

if ! command -v gcloud &>/dev/null; then
    echo "ERROR: gcloud CLI not found. Install from https://cloud.google.com/sdk/docs/install"
    exit 1
fi

ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)
if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "ERROR: No active gcloud account. Run: gcloud auth login"
    exit 1
fi
echo "    Authenticated as: $ACTIVE_ACCOUNT"

echo "    Setting project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID" --quiet

# ---------------------------------------------------------------------------
# 2. Enable APIs (idempotent)
# ---------------------------------------------------------------------------
echo "==> Enabling APIs"
gcloud services enable spanner.googleapis.com --quiet
gcloud services enable documentai.googleapis.com --quiet
echo "    APIs enabled."

# ---------------------------------------------------------------------------
# 3. Spanner free-trial instance (idempotent)
# ---------------------------------------------------------------------------
echo "==> Provisioning Spanner instance: $SPANNER_INSTANCE"
if gcloud spanner instances describe "$SPANNER_INSTANCE" &>/dev/null; then
    echo "    Instance already exists -- skipping."
else
    echo "    Creating free-trial instance..."
    gcloud spanner instances create "$SPANNER_INSTANCE" \
        --config="$SPANNER_CONFIG" \
        --description="TaxClarity Free Trial" \
        --instance-type=free-instance \
        --quiet
    echo "    Instance created."
fi

# ---------------------------------------------------------------------------
# 4. Spanner database (idempotent)
# ---------------------------------------------------------------------------
echo "==> Provisioning Spanner database: $SPANNER_DB"
if gcloud spanner databases describe "$SPANNER_DB" --instance="$SPANNER_INSTANCE" &>/dev/null; then
    echo "    Database already exists -- skipping."
else
    echo "    Creating database..."
    gcloud spanner databases create "$SPANNER_DB" --instance="$SPANNER_INSTANCE" --quiet
    echo "    Database created."
fi

# ---------------------------------------------------------------------------
# 5. Document AI processor (idempotent)
# ---------------------------------------------------------------------------
echo "==> Provisioning Document AI processor: $DOCAI_PROCESSOR_NAME"

ACCESS_TOKEN=$(gcloud auth print-access-token)
DOCAI_API="https://${DOCAI_LOCATION}-documentai.googleapis.com/v1/projects/${PROJECT_ID}/locations/${DOCAI_LOCATION}"

# Check if processor already exists
EXISTING=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
    "${DOCAI_API}/processors" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data.get('processors', []):
    if p.get('displayName') == '${DOCAI_PROCESSOR_NAME}':
        print(p['name'].split('/')[-1])
        break
" 2>/dev/null || true)

if [ -n "$EXISTING" ]; then
    echo "    Processor already exists -- ID: $EXISTING"
    PROCESSOR_ID="$EXISTING"
else
    echo "    Creating processor..."
    CREATE_RESP=$(curl -s -X POST \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"type\":\"${DOCAI_PROCESSOR_TYPE}\",\"displayName\":\"${DOCAI_PROCESSOR_NAME}\"}" \
        "${DOCAI_API}/processors")
    PROCESSOR_ID=$(echo "$CREATE_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
name = data.get('name', '')
print(name.split('/')[-1] if name else '')
" 2>/dev/null || true)

    if [ -z "$PROCESSOR_ID" ]; then
        echo "    WARNING: Could not extract processor ID from response:"
        echo "    $CREATE_RESP"
        echo "    You may need to create the processor manually."
    else
        echo "    Processor created -- ID: $PROCESSOR_ID"
    fi
fi

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================"
echo "  GCP Provisioning Complete"
echo "============================================"
echo "  Project:            $PROJECT_ID"
echo "  Spanner Instance:   $SPANNER_INSTANCE"
echo "  Spanner Database:   $SPANNER_DB"
echo "  Spanner Config:     $SPANNER_CONFIG"
echo "  Document AI Loc:    $DOCAI_LOCATION"
echo "  Document AI ID:     ${PROCESSOR_ID:-<unknown>}"
echo ""
echo "  Update your .env with:"
echo "    SPANNER_PROJECT_ID=$PROJECT_ID"
echo "    SPANNER_INSTANCE_ID=$SPANNER_INSTANCE"
echo "    SPANNER_DATABASE_ID=$SPANNER_DB"
echo "    DOCAI_LOCATION=$DOCAI_LOCATION"
echo "    DOCAI_PROCESSOR_ID=${PROCESSOR_ID:-<paste processor ID here>}"
echo "============================================"
