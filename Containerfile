# ── Stage 1: build Vue frontend ───────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json .
RUN npm install
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS backend
WORKDIR /app

# Install Python deps (no editable install needed in production)
COPY pyproject.toml .
RUN uv pip install --system \
    bleak \
    fastapi \
    uvicorn[standard]

# Copy application code
COPY src/ ./src/

# Copy built frontend so FastAPI can serve it as static files
COPY --from=frontend /build/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
