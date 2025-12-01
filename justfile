# Set the default command to list all available commands
default:
    @just --list

# clean up caches, virtual environment, and test artifacts
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
    GIT_LFS_SKIP_SMUDGE=1 uv sync --locked --extra dev {{OPTS}}
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
    uv run pytest --disable-pytest-warnings --color=yes --verbose -s --tb=short tests/relevance {{OPTS}}

# run linters and code formatters on relevant files
lint:
    uv run pre-commit run --show-diff-on-failure

# run linters and code formatters on all files
lint-all:
    uv run pre-commit run --all-files --show-diff-on-failure

# serve the API on a local development server with hot reloading
serve-api:
    uv run uvicorn api.main:app --reload
