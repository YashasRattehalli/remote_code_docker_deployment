FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    docker.io \
    git \
    curl \
    wget \
    tree \
    && rm -rf /var/lib/apt/lists/*

# Copy all project files
COPY pyproject.toml ./
COPY app/ ./app/
COPY run.py ./

# Install Python dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] docker pydantic pydantic-settings httpx python-multipart

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

# Run application as root (needed for Docker socket access)
CMD ["python", "run.py"] 