# Set the default command to list all available commands
default:
    @just --list

# install dependencies and set up the project
install +OPTS="":
    uv lock
    uv sync --locked --extra dev {{OPTS}}
    uv run pre-commit install --install-hooks

# test the project
test +OPTS="":
    uv run pytest --disable-pytest-warnings --color=yes --verbose {{OPTS}}

# run linters and code formatters on relevant files
lint:
    uv run pre-commit run --show-diff-on-failure

# run linters and code formatters on all files
lint-all:
    uv run pre-commit run --all-files --show-diff-on-failure
