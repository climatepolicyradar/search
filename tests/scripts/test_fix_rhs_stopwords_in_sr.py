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
STOPWORDS_TEXT = "\n".join(sorted(STOPWORDS)) + "\n"


def _load_script():
    spec = importlib.util.spec_from_file_location("fix_rhs_stopwords_in_sr", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


@pytest.mark.parametrize(
    ("line", "fixed_line", "removed"),
    [
        pytest.param(
            'gga +> ?"global goal on adaptation";\n',
            'gga +> ?"global goal adaptation";\n',
            ["on"],
            id="quoted-phrase-stopword",
        ),
        pytest.param(
            "x -> foo and bar;\n", "x -> foo bar;\n", ["and"], id="bare-stopword-term"
        ),
        pytest.param(
            'x +> ?"electric car" ?"electric vehicle"!50;\n',
            'x +> ?"electric car" ?"electric vehicle"!50;\n',
            [],
            id="marker-and-weight-preserved",
        ),
        pytest.param(
            'x +> ?"the methane and the carbon";\n',
            'x +> ?"methane carbon";\n',
            ["the", "and", "the"],
            id="multiple-stopwords-in-phrase",
        ),
        pytest.param(
            'x +> ?"greenhouse and gas" and ?"methane and carbon";\n',
            'x +> ?"greenhouse gas" ?"methane carbon";\n',
            ["and", "and", "and"],
            id="stopwords-in-multiple-phrases",
        ),
        pytest.param(
            "x -> methane is a greenhouse gas and carbon too;\n",
            "x -> methane is greenhouse gas carbon too;\n",
            ["a", "and"],
            id="multiple-stopwords-in-bare-terms",
        ),
        pytest.param(
            'x +> ?"greenhouse and gas" and methane;\n',
            'x +> ?"greenhouse gas" methane;\n',
            ["and", "and"],
            id="stopwords-in-mixed-terms",
        ),
        pytest.param("# a comment\n", "# a comment\n", [], id="comment-line"),
        pytest.param("@language(en)\n", "@language(en)\n", [], id="directive-line"),
        pytest.param("\n", "\n", [], id="blank-line"),
        pytest.param(
            'ndc +> ?"nationally determined contribution";\n',
            'ndc +> ?"nationally determined contribution";\n',
            [],
            id="clean-line",
        ),
    ],
)
def test_stopwords_are_removed_from_rhs(script, line, fixed_line, removed) -> None:
    """Stopwords are stripped from RHS terms; comments/directives/blanks/clean lines pass through."""
    assert script.remove_stopwords_from_line_rhs(line, STOPWORDS) == (fixed_line, removed)


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("this is not a rule\n", id="unparsable-line"),
        pytest.param('x +> ?"on the a";\n', id="all-stopword-phrase"),
        pytest.param("x +> [1];\n", id="unrecognised-term"),
    ],
)
def test_unfixable_lines_raise(script, line) -> None:
    """Lines the fixer can't safely handle raise rather than being silently skipped or mangled."""
    with pytest.raises(ValueError):
        script.remove_stopwords_from_line_rhs(line, STOPWORDS)


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


def _make_fake_rules_dir(tmp_path: Path, sr_contents: str) -> tuple[Path, Path]:
    """Build a bare rules dir + stopwords file under tmp_path for direct run() calls."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    stopwords_path = tmp_path / "stopwords.txt"
    stopwords_path.write_text(STOPWORDS_TEXT)
    (rules_dir / "passages.sr").write_text(sr_contents)
    return rules_dir, stopwords_path


def test_run_check_fails_and_does_not_write(script, tmp_path, capsys) -> None:
    """check=True exits non-zero, reports the offending word, and leaves the file untouched."""
    sr_with_stopword = 'gga +> ?"global goal on adaptation";\n'
    rules_dir, stopwords_path = _make_fake_rules_dir(tmp_path, sr_with_stopword)

    exit_code = script.run(rules_dir, stopwords_path, check=True, fix=False)

    assert exit_code == 1
    assert "'on'" in capsys.readouterr().out
    assert (rules_dir / "passages.sr").read_text() == sr_with_stopword


def test_run_check_reports_every_violation_not_just_the_first(script, tmp_path, capsys) -> None:
    """check=True lists every violation in the file, not only the first one it hits."""
    sr_contents = (
        'gga +> ?"global goal on adaptation";\n'
        "not a rule\n"
        'stopword +> ?"second on example";\n'
    )
    rules_dir, stopwords_path = _make_fake_rules_dir(tmp_path, sr_contents)

    exit_code = script.run(rules_dir, stopwords_path, check=True, fix=False)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert ":1:" in out
    assert ":2:" in out
    assert ":3:" in out


def test_run_check_flags_specific_stopwords_in_unfixable_phrase(script, tmp_path, capsys) -> None:
    """check=True names the exact stopwords even when the phrase can't be auto-fixed."""
    rules_dir, stopwords_path = _make_fake_rules_dir(tmp_path, 'gga +> ?"on the a";\n')

    exit_code = script.run(rules_dir, stopwords_path, check=True, fix=False)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "'on'" in out
    assert "'the'" in out
    assert "'a'" in out


def test_run_check_passes_on_clean_file(script, tmp_path) -> None:
    """check=True exits zero when no RHS entries contain stopwords."""
    rules_dir, stopwords_path = _make_fake_rules_dir(
        tmp_path, 'ndc +> ?"nationally determined contribution";\n'
    )

    exit_code = script.run(rules_dir, stopwords_path, check=True, fix=False)

    assert exit_code == 0


def test_run_fix_exits_nonzero_when_unfixable_line_remains(script, tmp_path) -> None:
    """fix=True still fixes what it can, but exits non-zero if something needs manual attention."""
    sr_contents = 'gga +> ?"global goal on adaptation";\nnot a rule\n'
    rules_dir, stopwords_path = _make_fake_rules_dir(tmp_path, sr_contents)

    exit_code = script.run(rules_dir, stopwords_path, check=False, fix=True)

    assert exit_code == 1
    assert (
        rules_dir / "passages.sr"
    ).read_text() == 'gga +> ?"global goal adaptation";\nnot a rule\n'


def test_cli_entrypoint_end_to_end(tmp_path: Path) -> None:
    """Smoke test for the actual `python3 <script>` entry point and its CLI defaults."""
    sr_with_stopword = 'gga +> ?"global goal on adaptation";\n'
    rules_dir = tmp_path / "vespa" / "app" / "rules"
    lucene_dir = tmp_path / "vespa" / "app" / "lucene-linguistics" / "en"
    rules_dir.mkdir(parents=True)
    lucene_dir.mkdir(parents=True)
    (lucene_dir / "stopwords.txt").write_text(STOPWORDS_TEXT)
    sr_path = rules_dir / "passages.sr"
    sr_path.write_text(sr_with_stopword)

    script_dir = tmp_path / "scripts" / "vespa_rules"
    script_dir.mkdir(parents=True)
    fake_script = script_dir / "fix_rhs_stopwords_in_sr.py"
    fake_script.write_text(SCRIPT_PATH.read_text())

    # no flags -> defaults to --check: reports, exits 1, writes nothing
    default_result = subprocess.run(
        [sys.executable, str(fake_script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert default_result.returncode == 1
    assert "'on'" in default_result.stdout
    assert sr_path.read_text() == sr_with_stopword

    # --fix alone (no explicit --no-check) fixes it and exits 0
    fix_result = subprocess.run(
        [sys.executable, str(fake_script), "--fix"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert fix_result.returncode == 0
    assert sr_path.read_text() == 'gga +> ?"global goal adaptation";\n'

    # a follow-up --check now passes
    check_result = subprocess.run(
        [sys.executable, str(fake_script), "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert check_result.returncode == 0
