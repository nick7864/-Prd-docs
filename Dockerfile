# PRD Triage Agent — Cloud Run deployment image
# Per spec D6 Decision: Deployment via Dockerfile + Cloud Run + agents-cli deploy
#
# Build:   docker build -t prd-triager .
# Run:     docker run -p 8080:8080 -e GOOGLE_API_KEY=... prd-triager
# Deploy:  adk deploy cloud_run --project <gcp-project> --region asia-east1

FROM python:3.12-slim

WORKDIR /app

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first (better layer caching for dep-only changes)
COPY pyproject.toml uv.lock ./

# Copy application source — MUST be before uv sync so hatchling can build the package
COPY src/ ./src/
COPY data/ ./data/

# Install production dependencies + project itself (no dev deps)
RUN uv sync --frozen --no-dev

# Sample PRDs and architecture docs are baked in for demo purposes.
# In production, mount a volume or configure a Git-backed data source.

# Cloud Run expects the app to listen on $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

# Run the FastAPI server via uvicorn
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
