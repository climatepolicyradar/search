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
    """Get the short hash of the current git commit."""
    try:
        git_commit_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        return git_commit_hash
    except Exception as e:
        raise RuntimeError("Could not determine the current git commit hash") from e


GIT_COMMIT_HASH = get_git_commit_hash()
REPO_ROOT_DIR = get_git_root()
DATA_DIR = REPO_ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

AWS_PROFILE_NAME = os.getenv("AWS_PROFILE_NAME", "labs")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME", "eu-west-1")

DATASET_NAME = "climatepolicyradar/all-document-text-data"
