# ------------------------------------------------------------------------------
# Production Dockerfile for Acme AI Customer Support Agent Platform
# Multi-stage / optimized slim build with non-root security & built-in healthcheck
# ------------------------------------------------------------------------------

FROM python:3.11-slim as runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Install curl for container healthchecking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source code and resources
COPY . .

# Create non-root system user for security hardening
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Launch production ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
