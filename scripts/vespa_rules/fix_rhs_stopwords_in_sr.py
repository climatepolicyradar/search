# Runs as a CI check that auto-fixes passages.sr, labels.sr. and documents.sr by removing stopwords from the right-hand side of the rules.

from pathlib import Path
import re

import typer

app = typer.Typer()

def load_stopwords(path: Path) -> set[str]:
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip().lower() for line in f}

# For vespa semantic rule documentation,see
# https://docs.vespa.ai/en/reference/querying/semantic-rules.html
TERM_MARKERS = "?=+$-"

def remove_stopwords_from_line_rhs(line: str, stopwords: set[str]) -> str:
    newline = "\n" if line.endswith("\n") else ""
    stripped = line.strip()

    # pass through comments, empty lines, and @-directives unchanged
    if not stripped or stripped.startswith("#") or stripped.startswith("@"):
        return line

    # match rule lines
    match = re.match(r"(?P<lhs>.*?)(?P<op>->|\+>)(?P<rhs>.*);\s*$", stripped)
    if match is None:
        raise ValueError(f"could not parse rule line: {line!r}")

    lhs, op, rhs = match["lhs"], match["op"], match["rhs"]

    # Each RHS term is a quoted phrase or a bare word, optionally preceded by
    # a single term-type marker (?=+$-) and optionally followed by a
    # `!weight` suffix - tokenise accordingly so phrases aren't split on
    # their internal whitespace, then filter out stopwords and reassemble.
    terms = re.findall(r'[?=+$-]?"[^"]*"(?:!\d+)?|\S+', rhs)
    fixed_terms = []
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
            words = [word for word in phrase.split() if word.lower() not in stopwords]
            if not words:
                raise ValueError(
                    f"every word in RHS phrase {term!r} is a stopword, "
                    f"cannot auto-fix: {line!r}"
                )
            fixed_terms.append(f'{marker}"{" ".join(words)}"{weight}')
            continue

        if not re.match(r"^[A-Za-z][\w'-]*$", body):
            raise ValueError(
                f"unrecognised RHS term {term!r} (labels and reference "
                f"productions like [..] / … aren't supported): {line!r}"
            )

        if body.lower() in stopwords:
            continue
        fixed_terms.append(f"{marker}{body}{weight}")

    if not fixed_terms:
        raise ValueError(f"RHS would be empty after removing stopwords: {line!r}")

    return f"{lhs.strip()} {op} {' '.join(fixed_terms)};{newline}"

def fix_file(path: Path, stopwords: set[str]) -> tuple[str, bool]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    fixed_lines = [remove_stopwords_from_line_rhs(line, stopwords) for line in lines]
    original_text = "".join(lines)
    fixed_text = "".join(fixed_lines)
    return fixed_text, fixed_text != original_text

@app.command()
def main(
    check: bool = typer.Option(
        False,
        "--check",
        help="report violations without fixing them",
    ),
) -> None:
    """Remove stopwords from RHS entries in vespa/app/rules/*.sr."""
    repo_root = Path(__file__).resolve().parents[2]
    rules_dir = repo_root / "vespa" / "app" / "rules"
    stopwords_path = (
        repo_root / "vespa" / "app" / "lucene-linguistics" / "en" / "stopwords.txt"
    )
    stopwords = load_stopwords(stopwords_path)

    files_needing_fix = []
    for sr_path in sorted(rules_dir.glob("*.sr")):
        fixed_text, changed = fix_file(sr_path, stopwords)
        if not changed:
            continue

        files_needing_fix.append(sr_path)
        if check:
            print(f"{sr_path} has RHS entries that spell out stopwords")
        else:
            sr_path.write_text(fixed_text, encoding="utf-8")
            print(f"Fixed {sr_path}")

    if check and files_needing_fix:
        print("Run `just fix-vespa-rules-stopwords` locally and commit the result.")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
