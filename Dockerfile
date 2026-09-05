# ==========================================
# Stage 1: Build the React 19 Frontend SPA
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/web

COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ==========================================
# Stage 2: Python 3.13 Runtime & Backend
# ==========================================
FROM python:3.13-slim AS runner
WORKDIR /app

# Install git (required by Groundtruth's git inspection adapters)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[api]"

# Copy source code, scoring policy, and demo snapshots
COPY src/ ./src/
COPY demo/ ./demo/
COPY scoring_policy.yaml .

# Copy compiled frontend from Stage 1 into FastAPI's static folder
COPY --from=frontend-builder /app/src/groundtruth/api/static ./src/groundtruth/api/static

# Default environment settings for web hosting
ENV GT_API_HOST=0.0.0.0
ENV GT_API_DEMO_MODE=true
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run uvicorn on the dynamic cloud host port ()
CMD ["sh", "-c", "uvicorn groundtruth.api.app:create_app --factory --host 0.0.0.0 --port "]
