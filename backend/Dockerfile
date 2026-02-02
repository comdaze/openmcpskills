# Open MCP Skills Server Dockerfile
# Multi-stage build for smaller production image
# Build context should be the parent directory (open-mcp-skills/)

# Stage 1: Build
FROM public.ecr.aws/docker/library/python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files (from backend/ relative to build context)
COPY backend/pyproject.toml backend/README.md ./

# Install dependencies
RUN pip install --no-cache-dir build && \
    pip install --no-cache-dir .

# Stage 2: Runtime
FROM public.ecr.aws/docker/library/python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 mcpuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (from backend/app relative to build context)
COPY backend/app ./app

# Copy skills directory (from skills/ relative to build context)
COPY skills ./skills

# Set ownership
RUN chown -R mcpuser:mcpuser /app

# Switch to non-root user
USER mcpuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SKILLS_DIR=/app/skills \
    HOST=0.0.0.0 \
    PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
