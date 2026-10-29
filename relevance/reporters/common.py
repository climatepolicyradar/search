import os


def branch() -> str:
    return os.getenv("GITHUB_REF_NAME", "local")
