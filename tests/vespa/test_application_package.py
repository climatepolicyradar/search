"""
Guards against files Vespa Cloud will refuse to deploy.

Vespa parses some directories of the application package and rejects anything
with an extension it does not recognise ("File in application package with
unknown extension"). Nothing else catches this: `vespa prod deploy` only submits
the package, so the deploy job goes green and the rejection happens later inside
Vespa Cloud, and the local Docker Vespa the e2e tests use is more permissive.
"""

from pathlib import Path

import pytest

VESPA_APP_DIR = Path(__file__).resolve().parents[2] / "vespa" / "app"

# Directories Vespa parses. Others (`lucene-linguistics`, `security`) may hold
# anything.
PARSED_DIRECTORIES: dict[str, set[str]] = {
    ".": {".xml"},
    "schemas": {".sd"},
    "rules": {".sr"},
    "search/query-profiles": {".xml"},
}


def _files_directly_in(directory: str) -> list[Path]:
    """Files in one directory of the application package, not recursing."""
    root = VESPA_APP_DIR if directory == "." else VESPA_APP_DIR / directory
    return sorted(path for path in root.glob("*") if path.is_file())


@pytest.mark.parametrize(("directory", "allowed"), PARSED_DIRECTORIES.items())
def test_application_package_has_no_files_vespa_will_reject(
    directory: str, allowed: set[str]
) -> None:
    """Every file in a directory Vespa parses must have an extension it accepts."""
    files = _files_directly_in(directory)
    assert files, f"{directory} is empty or missing - has the package moved?"

    unexpected = [path.name for path in files if path.suffix not in allowed]

    assert not unexpected, (
        f"vespa/app/{directory} contains {unexpected}, which Vespa Cloud will "
        f"reject on deploy. Only {sorted(allowed)} are allowed here. "
        "Move documentation to vespa/docs/."
    )
