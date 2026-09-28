# Runs as a CI check that auto-fixes passages.sr, labels.sr. and documents.sr by removing stopwords from the right-hand side of the rules.

import re
from dataclasses import dataclass
from pathlib import Path

import typer

app = typer.Typer()

def load_stopwords(path: Path) -> set[str]:
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines()}

# For vespa semantic rule documentation,see
# https://docs.vespa.ai/en/reference/querying/semantic-rules.html
TERM_MARKERS = "?=+$-"

@dataclass
class Violation:
    file: Path
    line_number: int
    line: str
    words: list[str]
    fixable: bool
    detail: str

class UnfixableRhsError(ValueError):
    """A rule line has a problem that can't be safely auto-fixed."""

    def __init__(self, message: str, words: list[str] | None = None) -> None:
        super().__init__(message)
        self.words = words or []

def remove_stopwords_from_line_rhs(
    line: str, stopwords: set[str]
) -> tuple[str, list[str]]:
    newline = "\n" if line.endswith("\n") else ""
    stripped = line.strip()

    # pass through comments, empty lines, and @-directives unchanged
    if not stripped or stripped.startswith("#") or stripped.startswith("@"):
        return line, []

    # match rule lines
    match = re.match(r"(?P<lhs>.*?)(?P<op>->|\+>)(?P<rhs>.*);\s*$", stripped)
    if match is None:
        raise UnfixableRhsError(f"could not parse rule line: {line!r}")

    lhs, op, rhs = match["lhs"], match["op"], match["rhs"]

    # Each RHS term is a quoted phrase or a bare word, optionally preceded by
    # a single term-type marker (?=+$-) and optionally followed by a
    # `!weight` suffix - tokenise accordingly so phrases aren't split on
    # their internal whitespace, then filter out stopwords and reassemble.
    terms = re.findall(r'[?=+$-]?"[^"]*"(?:!\d+)?|\S+', rhs)
    fixed_terms = []
    removed_words = []
    for term in terms:
        marker = ""
        body = term
        if body and body[0] in TERM_MARKERS:
            marker, body = body[0], body[1:]

        weight_match = re.search(r"!\d+$", body)
        weight = weight_match.group(0) if weight_match else ""
        if weight:
            body = body[: -len(weight)]

        quoted = re.match(r'^"([^"]*)"$', body)
        if quoted:
            phrase = quoted.group(1)
            words = []
            for word in phrase.split():
                if word.lower() in stopwords:
                    removed_words.append(word)
                else:
                    words.append(word)
            if not words:
                raise UnfixableRhsError(
                    f"every word in RHS phrase {term!r} is a stopword, "
                    f"cannot auto-fix: {line!r}",
                    words=phrase.split(),
                )
            fixed_terms.append(f'{marker}"{" ".join(words)}"{weight}')
            continue

        if not re.match(r"^[A-Za-z][\w'-]*$", body):
            raise UnfixableRhsError(
                f"unrecognised RHS term {term!r} (labels and reference "
                f"productions like [..] / … aren't supported): {line!r}"
            )

        if body.lower() in stopwords:
            removed_words.append(body)
            continue
        fixed_terms.append(f"{marker}{body}{weight}")

    if not fixed_terms:
        raise UnfixableRhsError(
            f"RHS would be empty after removing stopwords: {line!r}",
            words=removed_words,
        )

    fixed_line = f"{lhs.strip()} {op} {' '.join(fixed_terms)};{newline}"
    return fixed_line, removed_words

def fix_file(path: Path, stopwords: set[str]) -> tuple[str, list[Violation]]:
    """Fix every fixable line; return the rebuilt text and every violation found."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    fixed_lines = []
    violations: list[Violation] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            fixed_line, removed_words = remove_stopwords_from_line_rhs(line, stopwords)
        except UnfixableRhsError as e:
            fixed_lines.append(line)
            violations.append(
                Violation(
                    file=path,
                    line_number=line_number,
                    line=line.rstrip("\n"),
                    words=e.words,
                    fixable=False,
                    detail=str(e),
                )
            )
            continue

        fixed_lines.append(fixed_line)
        if removed_words:
            violations.append(
                Violation(
                    file=path,
                    line_number=line_number,
                    line=line.rstrip("\n"),
                    words=removed_words,
                    fixable=True,
                    detail=f"RHS spells out stopword(s): {removed_words}",
                )
            )

    return "".join(fixed_lines), violations

def _print_violation(violation: Violation) -> None:
    if violation.fixable:
        print(
            f"{violation.file}:{violation.line_number}: remove {violation.words} "
            f"from: {violation.line}"
        )
    elif violation.words:
        print(
            f"{violation.file}:{violation.line_number}: stopword(s) {violation.words} "
            f"found but can't be auto-removed here (needs a manual rewrite): "
            f"{violation.line}"
        )
    else:
        print(f"{violation.file}:{violation.line_number}: {violation.detail}")

def run(rules_dir: Path, stopwords_path: Path, check: bool, fix: bool) -> int:
    """Check/fix every *.sr file in rules_dir; return the process exit code."""
    stopwords = load_stopwords(stopwords_path)

    any_violations = False
    any_unresolved = False
    for sr_path in sorted(rules_dir.glob("*.sr")):
        fixed_text, violations = fix_file(sr_path, stopwords)
        if not violations:
            continue

        any_violations = True
        for violation in violations:
            _print_violation(violation)
            if not violation.fixable:
                any_unresolved = True

        if fix and any(v.fixable for v in violations):
            sr_path.write_text(fixed_text, encoding="utf-8")
            print(f"Fixed {sr_path}")

    if check and any_violations:
        print("Run `just fix-vespa-rules-stopwords` locally and commit the result.")
        return 1

    if fix and any_unresolved:
        print("Some lines could not be auto-fixed and need manual attention.")
        return 1

    return 0

@app.command()
def main(
    check: bool = typer.Option(
        True,
        "--check",
        help="report violations without fixing them",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="fix violations in-place (implies --no-check)",
    ),
) -> None:
    """Remove stopwords from RHS entries in vespa/app/rules/*.sr."""
    if fix:
        check = False
    repo_root = Path(__file__).resolve().parents[2]
    rules_dir = repo_root / "vespa" / "app" / "rules"
    stopwords_path = (
        repo_root / "vespa" / "app" / "lucene-linguistics" / "en" / "stopwords.txt"
    )

    exit_code = run(rules_dir, stopwords_path, check=check, fix=fix)
    if exit_code:
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
