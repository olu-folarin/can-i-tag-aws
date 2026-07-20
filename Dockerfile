# syntax=docker/dockerfile:1

# can-i-tag-aws
# Multi-stage build for minimal image size

FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Development image: runtime deps plus test/lint/type tooling and boto3, so the
# full suite runs identically on any host OS (macOS, Windows, Linux). Not the
# final stage, so `docker build` without a target still produces the slim
# runtime image that gets published.
FROM python:3.13-slim AS dev

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt requirements-rgtapi.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt -r requirements-rgtapi.txt

COPY . .

CMD ["pytest", "-q", "-m", "not integration"]


FROM python:3.13-slim AS runtime

WORKDIR /app

# Install runtime dependencies for lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Create output directories before switching user
RUN mkdir -p output history .cache && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add local pip packages to PATH
ENV PATH="/home/appuser/.local/bin:$PATH"

# Default command runs the primary detection script
CMD ["python", "-m", "can_i_tag_aws.detect_api_taggable"]

# Labels for GHCR
LABEL org.opencontainers.image.source="https://github.com/olu-folarin/can-i-tag-aws"
LABEL org.opencontainers.image.description="Detects AWS resources that cannot be tagged - can-i-tag-aws"
LABEL org.opencontainers.image.licenses="MIT"
