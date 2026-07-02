#!/usr/bin/env bash
# Deploy PRD Triage Agent to Google Cloud Run.
# Per spec D6.2: Decision: Deployment via Dockerfile + Cloud Run + agents-cli deploy
#
# Prerequisites:
#   - Docker Desktop installed and running
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GOOGLE_API_KEY exported in your environment
#   - A GCP project with billing enabled
#
# Usage:
#   export GOOGLE_API_KEY="your-key"
#   export GCP_PROJECT="your-project-id"
#   bash scripts/deploy.sh

set -euo pipefail

PROJECT="${GCP_PROJECT:-}"
REGION="${GCP_REGION:-asia-east1}"
SERVICE_NAME="prd-triager"

if [ -z "$PROJECT" ]; then
    echo "ERROR: Set GCP_PROJECT environment variable."
    echo "  export GCP_PROJECT=\"your-project-id\""
    exit 1
fi

if [ -z "${GOOGLE_API_KEY:-}" ]; then
    echo "ERROR: Set GOOGLE_API_KEY environment variable."
    exit 1
fi

echo "=== Step 1: Build Docker image ==="
docker build -t "$SERVICE_NAME" .

echo ""
echo "=== Step 2: Local smoke test ==="
docker run -d -p 8080:8080 \
    -e GOOGLE_API_KEY="$GOOGLE_API_KEY" \
    --name "${SERVICE_NAME}-test" \
    "$SERVICE_NAME" || true

sleep 3
echo "Health check:"
curl -sf http://localhost:8080/health && echo " ✅" || echo " ❌ (may need more time)"
echo ""
echo "Triage test (prd-003, should reject due to API key in PRD):"
curl -sf -X POST http://localhost:8080/triage \
    -H 'Content-Type: application/json' \
    -d '{"prd_id":"prd-003"}' | python3 -m json.tool | head -20 || true

docker stop "${SERVICE_NAME}-test" 2>/dev/null || true
docker rm "${SERVICE_NAME}-test" 2>/dev/null || true

echo ""
echo "=== Step 3: Deploy to Cloud Run ==="
echo "Project: $PROJECT"
echo "Region:  $REGION"
echo "Service: $SERVICE_NAME"
echo ""

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --project "$PROJECT" \
    --region "$REGION" \
    --set-env-vars "GOOGLE_API_KEY=$GOOGLE_API_KEY" \
    --allow-unauthenticated \
    --memory 1Gi \
    --timeout 120

echo ""
echo "=== Deploy complete! ==="
echo "Get the URL:"
gcloud run services describe "$SERVICE_NAME" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format 'value(status.url)'

echo ""
echo "Test the deployed endpoint:"
ENDPOINT=$(gcloud run services describe "$SERVICE_NAME" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format 'value(status.url)')
echo "curl -X POST ${ENDPOINT}/triage -H 'Content-Type: application/json' -d '{\"prd_id\":\"prd-001\"}'"
