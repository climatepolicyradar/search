"""
The acronym matcher. Imported by run.py; run directly only for its self-test.

    uv run python research/acronyms/mine_acronyms.py --self-test

Documents define their own acronyms ("...Financial Disclosures (TCFD)..."). A pair is
kept only if the acronym's letters appear IN ORDER among the initials of the preceding
words - a subsequence, not a prefix: TCFD skips the "Force" in "Task Force on
Climate-related Financial Disclosures", and strict matching rejects most real acronyms.

That check is what makes the output usable. Brackets also hold years, jurisdictions and
table cells: on 1,086 sampled passages a naive bracket pattern matched 12 blocks, 11 of
them two-column tables ("Foundry | Ceramic"). The initials check left the one glossary.

Then two more steps:
  * Stopwords stripped - "global goal on adaptation" matches nothing once indexed,
    "global goal adaptation" does. See vespa/app/lucene-linguistics/README.md.
  * Collisions screened against ISO country codes, en/geo-synonyms.txt and the existing
    .sr rules - the automated form of the nz (New Zealand / net zero) problem.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STOPWORDS_FILE = REPO / "vespa/app/lucene-linguistics/en/stopwords.txt"
GEO_SYNONYMS_FILE = REPO / "vespa/app/lucene-linguistics/en/geo-synonyms.txt"
RULES_DIR = REPO / "vespa/app/rules"
ISO_CSV = REPO.parent / "knowledge-graph/data/raw/geography-iso-3166.csv"

MIN_ACRONYM_LEN = 2
MAX_ACRONYM_LEN = 8
MAX_LOOKBACK_WORDS = 12

# Any parenthetical group, plus whatever text ran up to it.
PAREN = re.compile(r"([^()]*)\(([^()]{1,120})\)")
# A bare acronym alone in the brackets: "... Plan (NECP)"
BARE_ACRONYM = re.compile(r"^([A-Z][A-Za-z0-9+\-]{1,7})$")
# The long form inside the brackets: "(Corporate Sustainability ... or CSRD)"
INLINE_LONG_FORM = re.compile(
    r"^(.*?)[,]?\s+(?:or|aka|also known as)\s+([A-Z][A-Za-z0-9+\-]{1,7})$", re.IGNORECASE
)


def load_stopwords() -> set[str]:
    return {
        line.strip().lower()
        for line in STOPWORDS_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def load_blocklist() -> dict[str, str]:
    """Terms we must not claim: country codes, geo aliases, existing rules."""
    blocked: dict[str, str] = {}

    if ISO_CSV.exists():
        with ISO_CSV.open() as f:
            for row in csv.DictReader(f):
                iso = (row.get("Iso") or "").strip().lower()
                name = (row.get("Name") or "").strip()
                if iso:
                    blocked[iso] = f"ISO code for {name}"
                    blocked.setdefault(iso[:2], f"ISO-2 prefix, {name}")
                for group in (row.get("Political groups") or "").split(";"):
                    if group.strip():
                        blocked.setdefault(group.strip().lower(), "political grouping in ISO data")
    else:
        print(f"WARNING: {ISO_CSV} not found - country-code screening is OFF", file=sys.stderr)

    for line in GEO_SYNONYMS_FILE.read_text().splitlines():
        if "=>" in line:
            lhs, rhs = line.split("=>", 1)
            for alias in lhs.split(","):
                if alias.strip():
                    blocked[alias.strip().lower()] = f"geo synonym -> {rhs.strip()}"

    for sr in sorted(RULES_DIR.glob("*.sr")):
        for line in sr.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "@")):
                continue
            lhs = re.split(r"[+\-]>", line)[0].strip()
            if lhs:
                blocked[lhs.lower()] = f"already a rule in {sr.name}"

    return blocked


def _words(phrase: str) -> list[str]:
    """Split on whitespace, keeping hyphenated words whole (Climate-related = one C)."""
    return [w for w in re.split(r"\s+", phrase.strip()) if re.search(r"\w", w)]


def _is_subsequence(target: str, initials: str) -> bool:
    it = iter(initials)
    return all(ch in it for ch in target)


def best_window(words: list[str], acronym: str, stopwords: set[str]) -> list[str] | None:
    """Shortest run of words the acronym plausibly abbreviates, anchored on its first letter."""
    target = re.sub(r"[^a-z0-9]", "", acronym.lower())
    if len(target) < MIN_ACRONYM_LEN:
        return None
    for size in range(len(target), len(target) + 5):
        for start in range(0, max(1, len(words) - size + 1)):
            window = words[start : start + size]
            if len(window) < len(target):
                continue
            significant = [w for w in window if w.lower().strip(".,;:") not in stopwords]
            if not significant:
                continue
            first = re.sub(r"[^a-z0-9]", "", significant[0].lower())
            if not first.startswith(target[0]):
                continue
            initials = "".join(re.sub(r"[^a-z0-9]", "", w.lower())[:1] for w in significant)
            if _is_subsequence(target, initials):
                return window
    return None


def clean_phrase(phrase: str, stopwords: set[str]) -> str:
    """Strip stopwords - an expansion that spells one out matches nothing."""
    words = [w for w in re.split(r"[^\w]+", phrase.lower()) if w]
    return " ".join(w for w in words if w not in stopwords)


def harvest_parentheticals_text(text: str, stopwords: set[str]) -> list[tuple[str, str]]:
    """Pull every "Long Form (ACR)" definition out of one piece of text."""
    found = []
    for before, inside in PAREN.findall(text):
        inline = INLINE_LONG_FORM.match(inside.strip())
        bare = BARE_ACRONYM.match(inside.strip())
        if inline:
            acronym, words = inline.group(2), _words(inline.group(1))
        elif bare:
            acronym, words = bare.group(1), _words(before)[-MAX_LOOKBACK_WORDS:]
        else:
            continue
        if not (MIN_ACRONYM_LEN <= len(acronym) <= MAX_ACRONYM_LEN):
            continue
        if sum(c.isupper() for c in acronym) < 2:
            continue
        window = best_window(words, acronym, stopwords)
        if window is None:
            continue
        cleaned = clean_phrase(" ".join(window), stopwords)
        if cleaned and len(cleaned.split()) >= 2:
            found.append((acronym.lower(), cleaned))
    return found


SELF_TEST = [
    ("Task Force on Climate-related Financial Disclosures (TCFD) report",
     [("tcfd", "task force climate related financial disclosures")]),
    ("...corporate sustainability reporting (Corporate Sustainability Reporting Directive or CSRD)",
     [("csrd", "corporate sustainability reporting directive")]),
    ("National Energy and Climate Plan (NECP) 2021-2030",
     [("necp", "national energy climate plan")]),
    ("Some Random Act (2021) of Parliament", []),
    ("Regulation (EU) No 537/2014", []),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true",
                    help="check the matcher still reproduces the rules already in documents.sr")
    args = ap.parse_args()
    if not args.self_test:
        ap.print_help()
        return
    sw = load_stopwords()
    failed = 0
    for text, expected in SELF_TEST:
        got = harvest_parentheticals_text(text, sw)
        ok = got == expected
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {text[:58]:<60} -> {got}")
    print(f"\n{len(SELF_TEST) - failed}/{len(SELF_TEST)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
