FROM python:3.13-slim-bookworm

WORKDIR /app

# Install build essentials and curl for health checks
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# Install uv and dependencies
RUN pip install uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked

# Copy the application code
COPY api/ api/
COPY search/ search/
COPY data/ data/

# Expose the FastAPI server on port 8000
EXPOSE 8000

# Run the FastAPI server with uvicorn
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

