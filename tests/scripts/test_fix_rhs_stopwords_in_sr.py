"""End-to-end tests for scripts/vespa_rules/fix_rhs_stopwords_in_sr.py."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "vespa_rules"
    / "fix_rhs_stopwords_in_sr.py"
)

STOPWORDS = {"on", "the", "a", "and"}


def _load_script():
    spec = importlib.util.spec_from_file_location("fix_rhs_stopwords_in_sr", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def _make_fake_repo(tmp_path: Path, sr_contents: str) -> Path:
    """Lay out a fake repo dir mirroring the real one and copy the script into it."""
    rules_dir = tmp_path / "vespa" / "app" / "rules"
    lucene_dir = tmp_path / "vespa" / "app" / "lucene-linguistics" / "en"
    rules_dir.mkdir(parents=True)
    lucene_dir.mkdir(parents=True)
    (lucene_dir / "stopwords.txt").write_text("\n".join(sorted(STOPWORDS)) + "\n")
    (rules_dir / "passages.sr").write_text(sr_contents)

    script_dir = tmp_path / "scripts" / "vespa_rules"
    script_dir.mkdir(parents=True)
    fake_script = script_dir / "fix_rhs_stopwords_in_sr.py"
    fake_script.write_text(SCRIPT_PATH.read_text())
    return fake_script


def test_quoted_phrase_stopword_is_dropped(script) -> None:
    """The passages.sr regression: a stopword spelled out in a quoted RHS phrase is removed."""
    line = 'gga +> ?"global goal on adaptation";\n'
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (
        'gga +> ?"global goal adaptation";\n',
        ["on"],
    )


def test_bare_stopword_term_is_dropped(script) -> None:
    """A bare (unquoted) RHS term that is itself a stopword is dropped entirely."""
    line = "x -> foo and bar;\n"
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (
        "x -> foo bar;\n",
        ["and"],
    )


def test_marker_and_weight_are_preserved(script) -> None:
    """A term-type marker and a `!weight` suffix survive the fix unchanged."""
    line = 'x +> ?"electric car" ?"electric vehicle"!50;\n'
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (line, [])


def test_multiple_stopwords_in_phrase_are_dropped(script) -> None:
    """All stopwords in a quoted RHS phrase are removed, leaving the rest intact."""
    line = 'x +> ?"the methane and the carbon";\n'
    fixed_line, removed = script.remove_stopwords_from_line_rhs(line, STOPWORDS)
    assert fixed_line == 'x +> ?"methane carbon";\n'
    assert removed == ["the", "and", "the"]


def test_stopwords_in_multiple_phrases_are_dropped(script) -> None:
    """All stopwords in multiple RHS terms are removed, leaving the rest intact."""
    line = 'x +> ?"greenhouse and gas" and ?"methane and carbon";\n'
    fixed_line, removed = script.remove_stopwords_from_line_rhs(line, STOPWORDS)
    assert fixed_line == 'x +> ?"greenhouse gas" ?"methane carbon";\n'
    assert removed == ["and", "and", "and"]


def test_multiple_stopwords_in_bare_terms_are_dropped(script) -> None:
    """All stopwords in multiple bare RHS terms are removed, leaving the rest intact."""
    line = "x -> methane is a greenhouse gas and carbon too;\n"
    fixed_line, removed = script.remove_stopwords_from_line_rhs(line, STOPWORDS)
    assert fixed_line == "x -> methane is greenhouse gas carbon too;\n"
    assert removed == ["a", "and"]


def test_stopwords_in_mixed_terms_are_dropped(script) -> None:
    """All stopwords in a mix of quoted and bare RHS terms are removed, leaving the rest intact."""
    line = 'x +> ?"greenhouse and gas" and methane;\n'
    fixed_line, removed = script.remove_stopwords_from_line_rhs(line, STOPWORDS)
    assert fixed_line == 'x +> ?"greenhouse gas" methane;\n'
    assert removed == ["and", "and"]


@pytest.mark.parametrize("line", ["# a comment\n", "@language(en)\n", "\n"])
def test_comment_directive_and_blank_lines_are_unchanged(script, line) -> None:
    """Comments, @-directives, and blank lines pass through untouched."""
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (line, [])


def test_clean_line_is_unchanged(script) -> None:
    """A rule with no stopwords in its RHS is returned unchanged."""
    line = 'ndc +> ?"nationally determined contribution";\n'
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (line, [])


def test_unparsable_rule_line_raises(script) -> None:
    """A non-comment/directive/blank line that isn't a valid `LHS OP RHS;` rule raises."""
    with pytest.raises(ValueError):
        script.remove_stopwords_from_line_rhs("this is not a rule\n", STOPWORDS)


def test_all_stopword_phrase_raises(script) -> None:
    """A quoted phrase made entirely of stopwords can't be auto-fixed, so it raises."""
    with pytest.raises(ValueError):
        script.remove_stopwords_from_line_rhs('x +> ?"on the a";\n', STOPWORDS)


def test_unrecognised_term_raises(script) -> None:
    """Reference productions (`[..]`) and labelled terms aren't supported and raise."""
    with pytest.raises(ValueError):
        script.remove_stopwords_from_line_rhs("x +> [1];\n", STOPWORDS)


def test_fix_file_reports_no_violations_for_clean_file(script, tmp_path: Path) -> None:
    """fix_file returns no violations and byte-identical text for an already-clean file."""
    sr_path = tmp_path / "clean.sr"
    original = '@language(en)\nndc +> ?"nationally determined contribution";\n'
    sr_path.write_text(original)

    text, violations = script.fix_file(sr_path, STOPWORDS)

    assert violations == []
    assert text == original


def test_fix_file_fixes_and_preserves_line_structure(script, tmp_path: Path) -> None:
    """fix_file rewrites only the offending line and doesn't introduce extra blank lines."""
    sr_path = tmp_path / "has_stopword.sr"
    sr_path.write_text('# comment\ngga +> ?"global goal on adaptation";\nlaw +> ?act;\n')

    text, violations = script.fix_file(sr_path, STOPWORDS)

    assert text == '# comment\ngga +> ?"global goal adaptation";\nlaw +> ?act;\n'
    assert len(violations) == 1
    assert violations[0].line_number == 2
    assert violations[0].words == ["on"]


def test_fix_file_collects_every_violation_instead_of_stopping_at_the_first(
    script, tmp_path: Path
) -> None:
    """A file with several independent problems reports all of them in one pass."""
    sr_path = tmp_path / "many_problems.sr"
    sr_path.write_text(
        'gga +> ?"global goal on adaptation";\n'
        "not a rule\n"
        'ok +> ?"clean rule here";\n'
        'stopword +> ?"second on example";\n'
    )

    _, violations = script.fix_file(sr_path, STOPWORDS)

    assert [v.line_number for v in violations] == [1, 2, 4]
    assert violations[0].words == ["on"]
    assert violations[0].fixable is True
    assert violations[1].words == []
    assert violations[1].fixable is False
    assert "could not parse" in violations[1].detail
    assert violations[2].words == ["on"]
    assert violations[2].fixable is True


def test_fix_file_reports_unfixable_line_as_violation_without_raising(
    script, tmp_path: Path
) -> None:
    """An unfixable line becomes a violation (with an explanatory detail) rather than raising."""
    sr_path = tmp_path / "broken.sr"
    sr_path.write_text('gga +> ?"on the a";\n')

    text, violations = script.fix_file(sr_path, STOPWORDS)

    assert text == 'gga +> ?"on the a";\n'
    assert len(violations) == 1
    assert violations[0].fixable is False
    assert "stopword" in violations[0].detail


def test_fix_file_names_the_stopwords_in_an_unfixable_phrase(
    script, tmp_path: Path
) -> None:
    """Even a phrase that can't be auto-fixed still reports exactly which words are stopwords."""
    sr_path = tmp_path / "broken.sr"
    sr_path.write_text('gga +> ?"on the a";\n')

    _, violations = script.fix_file(sr_path, STOPWORDS)

    assert violations[0].words == ["on", "the", "a"]


def test_check_mode_fails_and_does_not_write(tmp_path: Path) -> None:
    """`--check` exits non-zero, reports the offending word, and leaves the file untouched."""
    sr_with_stopword = 'gga +> ?"global goal on adaptation";\n'
    fake_script = _make_fake_repo(tmp_path, sr_with_stopword)

    result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "'on'" in result.stdout
    assert (
        tmp_path / "vespa" / "app" / "rules" / "passages.sr"
    ).read_text() == sr_with_stopword


def test_check_mode_reports_every_violation_not_just_the_first(tmp_path: Path) -> None:
    """`--check` lists every violation in the file, not only the first one it hits."""
    sr_contents = (
        'gga +> ?"global goal on adaptation";\n'
        "not a rule\n"
        'stopword +> ?"second on example";\n'
    )
    fake_script = _make_fake_repo(tmp_path, sr_contents)

    result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert ":1:" in result.stdout
    assert ":2:" in result.stdout
    assert ":3:" in result.stdout


def test_check_mode_flags_specific_stopwords_in_unfixable_phrase(tmp_path: Path) -> None:
    """`--check` names the exact stopwords even when the phrase can't be auto-fixed."""
    fake_script = _make_fake_repo(tmp_path, 'gga +> ?"on the a";\n')

    result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "'on'" in result.stdout
    assert "'the'" in result.stdout
    assert "'a'" in result.stdout


def test_check_mode_passes_on_clean_file(tmp_path: Path) -> None:
    """`--check` exits zero when no RHS entries contain stopwords."""
    clean_sr = 'ndc +> ?"nationally determined contribution";\n'
    fake_script = _make_fake_repo(tmp_path, clean_sr)

    result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


def test_fix_mode_rewrites_file_and_subsequent_check_passes(tmp_path: Path) -> None:
    """Running without `--check` fixes the file in place; a follow-up `--check` then exits 0."""
    sr_with_stopword = 'gga +> ?"global goal on adaptation";\n'
    fake_script = _make_fake_repo(tmp_path, sr_with_stopword)
    sr_path = tmp_path / "vespa" / "app" / "rules" / "passages.sr"

    fix_result = subprocess.run(
        [sys.executable, str(fake_script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert fix_result.returncode == 0
    assert sr_path.read_text() == 'gga +> ?"global goal adaptation";\n'

    check_result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert check_result.returncode == 0


def test_fix_mode_exits_nonzero_when_unfixable_line_remains(tmp_path: Path) -> None:
    """Fix mode still fixes what it can, but exits non-zero if something needs manual attention."""
    sr_contents = 'gga +> ?"global goal on adaptation";\nnot a rule\n'
    fake_script = _make_fake_repo(tmp_path, sr_contents)
    sr_path = tmp_path / "vespa" / "app" / "rules" / "passages.sr"

    result = subprocess.run(
        [sys.executable, str(fake_script)], cwd=tmp_path, capture_output=True, text=True
    )

    assert result.returncode == 1
    assert sr_path.read_text() == 'gga +> ?"global goal adaptation";\nnot a rule\n'
