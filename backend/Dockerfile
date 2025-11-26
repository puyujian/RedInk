# Stage 1: Base image with Python and uv
FROM python:3.11-slim as base

# Install uv package manager
RUN pip install --no-cache-dir uv

WORKDIR /app

# Stage 2: Dependencies
FROM base as dependencies

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Stage 3: Production
FROM base as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application code
COPY backend /app/backend
COPY image_providers.yaml.example /app/image_providers.yaml.example

# Create necessary directories
RUN mkdir -p /app/output /app/history

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=12398

# Expose port
EXPOSE 12398

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:12398/ || exit 1

# Run the application
CMD ["python", "-m", "backend.app"]
