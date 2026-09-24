set dotenv-load := true

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
    GIT_LFS_SKIP_SMUDGE=1 uv sync --group dev --group research {{ OPTS }}

# setup the project
setup: install
    trunk git-hooks sync
    uv run ipython kernel install --user

# test the project
test +OPTS="":
    uv run pytest --disable-pytest-warnings --color=yes --verbose {{ OPTS }}

# test only the functional behaviour of the code (not relevance)
test-functional +OPTS="":
    uv run pytest --disable-pytest-warnings --color=yes --verbose --ignore=relevance_tests {{ OPTS }}

# test only the relevance of search results
test-relevance +OPTS="":
    uv run relevance_tests/test_labels.py {{ OPTS }}
    uv run relevance_tests/test_passages.py {{ OPTS }}
    uv run relevance_tests/test_documents.py {{ OPTS }}

# run linters and code formatters on relevant files
lint:
    trunk check --fix

# run linters and code formatters on all files
lint-all:
    trunk check --all --fix

# serve the API on a local development server with hot reloading
serve-api:
    uv run uvicorn api.main:app --reload --port 8080

# Build Docker image for deployment
build-image:
    docker build --file api/Dockerfile --platform=linux/amd64 --progress=plain -t ${DOCKER_REGISTRY}/search-api:latest .

# Run Docker image locally
run-image cmd="sh":
    docker run --rm -it ${DOCKER_REGISTRY}/search-api:latest {{ cmd }}

# Login to AWS ECR
ecr-login:
    aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${DOCKER_REGISTRY}

# Push Docker image to ECR. Always pushes :latest; also pushes :{{ tag }} when provided.
push-image tag="":
    docker push ${DOCKER_REGISTRY}/search-api:latest
    if [ -n "{{ tag }}" ]; then docker tag ${DOCKER_REGISTRY}/search-api:latest ${DOCKER_REGISTRY}/search-api:{{ tag }} && docker push ${DOCKER_REGISTRY}/search-api:{{ tag }}; fi

# Deploy flows to Prefect Cloud (build, push, and register)
deploy-flows-from-local:
    echo building ${DOCKER_REGISTRY}/search-api:latest in region: ${AWS_REGION}
    just ecr-login
    just build-image
    just push-image
    uv run python deployments.py

get-version:
    @grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'

# region prefect
prefect-build:
    docker build --file ./prefect/Dockerfile --platform=linux/amd64 --progress=plain -t ${DOCKER_REGISTRY}/search-prefect:latest .

prefect-push:
    docker push ${DOCKER_REGISTRY}/search-prefect:latest

prefect-deploy:
    uv run python deployments.py

# endregion

vespa-query query instance="":
    #!/usr/bin/env bash
    set -e
    if [ -n "{{ instance }}" ]; then
        vespa_read_token=$(aws ssm get-parameter --name "/search/vespa-dev/read_token" --query "Parameter.Value" --output text --with-decryption)
        vespa_endpoint=$(aws ssm get-parameter --name "/search/vespa-dev/{{ instance }}" --query "Parameter.Value" --output text --with-decryption)
    else
        vespa_read_token=$(aws ssm get-parameter --name "/search/vespa/read_token" --query "Parameter.Value" --output text --with-decryption)
        vespa_endpoint=$(aws ssm get-parameter --name "/search/vespa/endpoint" --query "Parameter.Value" --output text --with-decryption)
    fi
    uv run vespa query \
        --target "$vespa_endpoint" \
        --header "Authorization: Bearer $vespa_read_token" \
        "{{ query }}"

# @related: PREFECT_VERSION
# check prefect is pinned to one exact version everywhere we declare it
check-prefect-version:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"

    pins=""
    status=0

    # `prefect` dependency specs (not `prefect-*`) in every pyproject.toml
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        where=$(echo "$hit" | cut -d: -f1,2)
        spec=$(echo "$hit" | sed -E 's/.*"(prefect(\[[^]]*\])?([=<>!~][^"]*)?)".*/\1/')
        version=$(echo "$spec" | sed -nE 's/^prefect(\[[^]]*\])?==([0-9]+(\.[0-9]+)+)$/\2/p')
        if [ -z "$version" ]; then
            echo "❌ $where: prefect must be pinned with == (found \"$spec\")"
            status=1
        else
            pins="${pins}${version}|${where}"$'\n'
        fi
    done < <(git grep -nE '"prefect(\[[^]]*\])?([=<>!~][^"]*)?"' -- '*pyproject.toml' || true)

    # prefect base images in every Dockerfile
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        where=$(echo "$hit" | cut -d: -f1,2)
        version=$(echo "$hit" | sed -nE 's|.*prefecthq/prefect:([0-9]+\.[0-9]+\.[0-9]+)([-[:space:]].*)?$|\1|p')
        if [ -z "$version" ]; then
            echo "❌ $where: prefect base image must use an exact version tag ($(echo "$hit" | cut -d: -f3-))"
            status=1
        else
            pins="${pins}${version}|${where}"$'\n'
        fi
    done < <(git grep -nE '^FROM +prefecthq/prefect:' -- '*Dockerfile*' || true)

    # the version each uv.lock actually resolved to
    for lock in $(git ls-files '*uv.lock'); do
        version=$(grep -A1 '^name = "prefect"$' "$lock" | sed -nE 's/^version = "([0-9]+(\.[0-9]+)+)"$/\1/p' || true)
        if [ -n "$version" ]; then
            pins="${pins}${version}|${lock}"$'\n'
        fi
    done

    if [ -z "$pins" ]; then
        echo "❌ no prefect version pins found - this check has gone stale"
        exit 1
    fi

    if [ "$(printf '%s' "$pins" | cut -d'|' -f1 | sort -u | wc -l | tr -d ' ')" -ne 1 ]; then
        echo "❌ prefect versions differ across the repo:"
        status=1
    fi

    printf '%s' "$pins" | sort | awk -F'|' '{ printf "  %-10s %s\n", $1, $2 }'

    if [ "$status" -ne 0 ]; then
        echo
        echo "Pin the same prefect version in every pyproject.toml, uv.lock and Dockerfile."
        echo "Run 'uv lock' in each directory after changing a pyproject.toml."
        exit 1
    fi

    echo "✅ prefect is pinned to the same version everywhere"
