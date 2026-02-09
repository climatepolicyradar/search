FROM python:3.13-slim-bookworm

WORKDIR /app

# Install build essentials, curl for health checks, and git for git dependencies
RUN apt-get update && apt-get install -y build-essential curl git && rm -rf /var/lib/apt/lists/*

# Install uv and dependencies
RUN pip install uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked

# Copy the application code
COPY api/ api/
COPY search/ search/

# Create data directory (will be populated from S3 at runtime)
RUN mkdir -p /app/data

# Expose the FastAPI server on port 8080
EXPOSE 8080

# Run the FastAPI server with uvicorn
# The lifespan event will download data from S3 before starting
CMD ["uv", "run", "fastapi", "run", "./api/main.py", "--host", "0.0.0.0", "--port", "8080"]
