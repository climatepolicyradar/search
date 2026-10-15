"""
Detect whether a change touches the Lucene linguistics configuration.

Vespa decides a deploy needs reindexing by diffing the `indexing:` scripts in
the schemas (`IndexingScriptChangeValidator`). The Lucene config lives in
`services.xml` and `lucene-linguistics/`, so changing an analyser, stemmer,
tokenizer, filter or the stopwords list changes which tokens get indexed
*without Vespa noticing* — the deploy succeeds and no reindex is triggered.

`services.xml` also holds unrelated config (nodes, resources, content cluster),
so we compare only the LuceneLinguistics component rather than the whole file.
The component is located by parsing the XML, and anything unexpected (missing
component, unparsable file) is reported as a change so the check fails closed.

Hit during FUS-568; see vespa/app/lucene-linguistics/README.md.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET  # nosec B405 - parses a file from this repo, not untrusted input
from pathlib import Path

SERVICES = "vespa/app/services.xml"
LINGUISTICS_DIR = "vespa/app/lucene-linguistics"
LINGUISTICS_CLASS = "com.yahoo.language.lucene.LuceneLinguistics"


class LinguisticsNotFound(Exception):
    """The LuceneLinguistics component wasn't where we expect it."""


def _canonicalise(element: ET.Element) -> str:
    """
    Serialise an element so semantically equal config compares equal.

    Attribute order and insignificant whitespace vary with formatting, and we
    only care about changes that alter how text is analysed.
    """
    for node in element.iter():
        node.tail = None
        if node.text is not None:
            node.text = node.text.strip() or None
    return ET.canonicalize(ET.tostring(element, encoding="unicode"))


def extract_linguistics(services_xml: str) -> str:
    """
    Return a canonical form of the LuceneLinguistics component.

    Raises LinguisticsNotFound if the file can't be parsed or the component
    isn't present, so callers can fail closed rather than silently pass.
    """
    try:
        root = ET.fromstring(services_xml)  # nosec B314 - services.xml is version-controlled in this repo
    except ET.ParseError as exc:
        raise LinguisticsNotFound(f"could not parse {SERVICES}: {exc}") from exc

    matches = [
        component
        for component in root.iter("component")
        if component.get("id") == LINGUISTICS_CLASS
        or component.get("class") == LINGUISTICS_CLASS
    ]
    if not matches:
        raise LinguisticsNotFound(
            f"no <component> with id or class '{LINGUISTICS_CLASS}' in {SERVICES}"
        )
    if len(matches) > 1:
        raise LinguisticsNotFound(
            f"expected one LuceneLinguistics component in {SERVICES}, found {len(matches)}"
        )
    return _canonicalise(matches[0])


def git_show(ref: str, path: str) -> str | None:
    """Return a file's contents at a ref, or None if it doesn't exist there."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def changed_files(base: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def services_linguistics_changed(base: str) -> tuple[bool, str]:
    """Compare the linguistics component between base and the working tree."""
    before = git_show(base, SERVICES)
    after = Path(SERVICES).read_text() if Path(SERVICES).exists() else None

    if before is None and after is None:
        return False, ""
    if before is None or after is None:
        return True, f"{SERVICES} (added or removed)"

    try:
        changed = extract_linguistics(before) != extract_linguistics(after)
    except LinguisticsNotFound as exc:
        # Fail closed: if we can't locate the component we can't rule out a
        # change, so warn rather than stay silent.
        return True, f"{SERVICES} (could not compare: {exc})"

    return changed, f"{SERVICES} (LuceneLinguistics component)" if changed else ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_linguistics_change.py <base-ref>", file=sys.stderr)
        return 2
    base = sys.argv[1]

    reasons = []

    # Anything under lucene-linguistics/ (stopwords, synonyms, configDir
    # contents) counts, except markdown, which is prose.
    for path in changed_files(base):
        if path.startswith(f"{LINGUISTICS_DIR}/") and not path.endswith(".md"):
            reasons.append(path)

    changed, reason = services_linguistics_changed(base)
    if changed:
        reasons.append(reason)

    if reasons:
        print("changed=true")
        print("Linguistics config changed in:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("changed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
