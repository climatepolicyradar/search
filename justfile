set dotenv-load

# Set the default command to list all available commands
default:
    @just --list

# Useful when you want to clear your local caches, your virtual environment, or the test artifacts and start from scratch. Should be followed by `just install` to get your repo back to a clean state.
clean:
    uv cache clean
    uv cache prune
    rm -rf .venv
    rm -rf .uv/cache
    rm -rf .pytest_cache
    rm -rf .hypothesis
    rm -rf .ruff_cache
    rm -rf .mypy_cache
    rm -rf .coverage
    rm -rf htmlcov

# install dependencies and set up the project
install +OPTS="":
    GIT_LFS_SKIP_SMUDGE=1 uv sync --locked --group dev {{OPTS}}

# setup the project
setup: install
    uv run pre-commit install --install-hooks
    uv run ipython kernel install --user

# test the project
test +OPTS="":
    uv run pytest --disable-pytest-warnings --color=yes --verbose {{OPTS}}

# test only the functional behavior of the code (not relevance)
test-functional +OPTS="":
    uv run pytest --disable-pytest-warnings --color=yes --verbose --ignore=tests/relevance {{OPTS}}

# test only the relevance of search results
test-relevance +OPTS="":
    uv run relevance_tests/test_labels.py {{OPTS}}
    uv run relevance_tests/test_passages.py {{OPTS}}
    uv run relevance_tests/test_documents.py {{OPTS}}

# run linters and code formatters on relevant files
lint:
    uv run pre-commit run --show-diff-on-failure

# run linters and code formatters on all files
lint-all:
    uv run pre-commit run --all-files --show-diff-on-failure

# serve the API on a local development server with hot reloading
serve-api:
    uv run uvicorn api.main:app --reload --port 8080

# Build Docker image for deployment
build-image:
    docker build --file api/Dockerfile --platform=linux/amd64 --progress=plain -t ${DOCKER_REGISTRY}/${DOCKER_REPOSITORY}:${VERSION} .

# Run Docker image locally
run-image cmd="sh":
    docker run --rm -it ${DOCKER_REGISTRY}/${DOCKER_REPOSITORY}:${VERSION} {{cmd}}

# Login to AWS ECR
ecr-login:
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${DOCKER_REGISTRY}

# Push Docker image to ECR
push-image:
    docker push ${DOCKER_REGISTRY}/${DOCKER_REPOSITORY}:${VERSION}

# Deploy flows to Prefect Cloud (build, push, and register)
deploy-flows-from-local:
    echo building ${DOCKER_REGISTRY}/${DOCKER_REPOSITORY}:${VERSION} in region: ${AWS_REGION}
    just ecr-login
    just build-image
    just push-image
    uv run python deployments.py

get-version:
    @grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'

# Dev
setup-api:
    # this recipe is needed to get you initially setup, but does not need to run continuously
    just gen-api-env

dev:
    uv run fastapi dev ./api/dev.py --port 8000

gen-api-env:
    #!/usr/bin/env bash
    set -euxo pipefail
    vespa_read_token=$(aws ssm get-parameter --name "/search/vespa/read_token" --query "Parameter.Value" --output text --with-decryption)
    vespa_endpoint=$(aws ssm get-parameter --name "/search/vespa/endpoint" --query "Parameter.Value" --output text --with-decryption)
    echo "VESPA_READ_TOKEN=$vespa_read_token" > ./api/.env
    echo "VESPA_ENDPOINT=$vespa_endpoint" >> ./api/.env

