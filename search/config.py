import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_git_root() -> Path:
    """Get the root directory of the git repository."""
    try:
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], universal_newlines=True
        ).strip()
        return Path(git_root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If we're not in a git repo or git isn't installed,
        # make a reasonable guess at the root directory
        return Path(__file__).parent.parent


def get_git_commit_hash() -> str:
    """
    Get the short hash of the current git commit.

    Priority:
    1. GIT_COMMIT_HASH environment variable (set by CI/CD or deployment)
    2. git rev-parse command (if in a git repository)
    3. Fallback to "unknown" if neither is available
    """
    # First, check whether the git commit hash is provided via environment variable
    if env_hash := os.getenv("GIT_COMMIT_HASH"):
        return env_hash

    # If not, try to get it from git
    try:
        git_commit_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        return git_commit_hash
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If we can't determine the git hash, return a fallback value
        # This should be acceptable in containerized environments.
        return "unknown"


def is_truthy(value: str | bool) -> bool:
    """
    Whether a string (e.g. in an environment variable) expresses a true state.

    If the value is a boolean, returns the boolean.
    """

    if isinstance(value, bool):
        return value

    return value == "1" or value.lower() == "true"


REPO_ROOT_DIR = get_git_root()

# DATA_DIR depends on the environment:
# - In deployed containers (ECS), use the DATA_DIR environment variable
# - In local development, use REPO_ROOT_DIR/data
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Path stems to use for storing primitives locally. Can be suffixed with the file
# extension for the search engine.
LABELS_PATH_STEM = DATA_DIR / "labels"
DOCUMENTS_PATH_STEM = DATA_DIR / "documents"
PASSAGES_PATH_STEM = DATA_DIR / "passages"

# test results directory
TEST_RESULTS_DIR = DATA_DIR / "test_results"


# AWS_PROFILE is only used in local development. In deployed containers (ECS),
# boto3 automatically uses the task IAM role, so the value should be None.
AWS_PROFILE = os.getenv("AWS_PROFILE", None)
AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")

DATASET_NAME = "climatepolicyradar/all-document-text-data"

# Weights & Biases
WANDB_ENTITY = "climatepolicyradar"
WANDB_PROJECT_OFFLINE_TESTS = "search_offline_tests"
DISABLE_WANDB = is_truthy(os.getenv("DISABLE_WANDB", False))
