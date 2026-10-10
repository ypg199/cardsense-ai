#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build and deploy the CardSense API to Google Cloud Run.
#
#   gcloud auth login
#   gcloud config set project <your-project-id>
#   ./deploy/cloudrun.sh
#
# The first run enables the APIs it needs, creates the Artifact Registry repo
# and asks for MONGODB_URI and GEMINI_API_KEY, which it stores in Secret
# Manager. Later runs just build and roll out a new revision.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
# Singapore: close to India, and supports Cloud Run custom domain mappings
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-cardsense-api}"
REPO="${REPO:-cardsense}"

if [[ -z "$PROJECT_ID" ]]; then
  echo "No project set. Run: gcloud config set project <your-project-id>" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/api:$(git rev-parse --short HEAD 2>/dev/null || date +%s)"

echo "→ Enabling APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com --project "$PROJECT_ID"

if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  echo "→ Creating Artifact Registry repo $REPO"
  gcloud artifacts repositories create "$REPO" --repository-format docker \
    --location "$REGION" --project "$PROJECT_ID"
fi

ensure_secret() {
  local name="$1" prompt="$2" value
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    return
  fi
  read -rsp "$prompt: " value
  echo
  printf '%s' "$value" | gcloud secrets create "$name" --data-file=- \
    --replication-policy automatic --project "$PROJECT_ID"
}
ensure_secret mongodb-uri "MongoDB Atlas connection string (MONGODB_URI)"
ensure_secret gemini-api-key "Gemini API key (GEMINI_API_KEY)"

# Cloud Run's default runtime account needs to read the two secrets
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format 'value(projectNumber)')"
RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
for secret in mongodb-uri gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$secret" --project "$PROJECT_ID" \
    --member "serviceAccount:$RUNTIME_SA" --role roles/secretmanager.secretAccessor >/dev/null
done

echo "→ Building $IMAGE"
gcloud builds submit --project "$PROJECT_ID" --config deploy/cloudbuild.yaml \
  --substitutions "_IMAGE=$IMAGE" .

echo "→ Deploying $SERVICE to $REGION"
# max-instances caps the bill; the timeout covers multi-month statement parses
gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --allow-unauthenticated \
  --port 8000 \
  --memory 1Gi \
  --cpu 1 \
  --cpu-boost \
  --concurrency 20 \
  --min-instances 0 \
  --max-instances 2 \
  --timeout 600 \
  --env-vars-file deploy/cloudrun.env.yaml \
  --set-secrets "MONGODB_URI=mongodb-uri:latest,GEMINI_API_KEY=gemini-api-key:latest"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')"
echo
echo "✓ Deployed: $URL"
echo "  Health check: curl $URL/health"
