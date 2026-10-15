"""End-to-end tests for scripts/vespa_linguistics/check_linguistics_change.py."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "vespa_linguistics"
    / "check_linguistics_change.py"
)

SERVICES_TEMPLATE = """<?xml version="1.0" encoding="utf-8" ?>
<services version="1.0">
    <container id="default" version="1.0">
        <component id="com.yahoo.language.lucene.LuceneLinguistics"
                   bundle="lucene-linguistics">
            <config name="com.yahoo.language.lucene.lucene-analysis">
                <configDir>lucene-linguistics</configDir>
                <analysis>
                    <item>
                        <name>{stemmer}</name>
                    </item>
                </analysis>
            </config>
        </component>
        <nodes count="{nodes}">
            <resources vcpu="2" memory="8Gb" disk="50Gb"/>
        </nodes>
    </container>
</services>
"""


def _load_script():
    spec = importlib.util.spec_from_file_location("check_linguistics_change", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with a services.xml and a linguistics dir, one commit on main."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")

    services = tmp_path / "vespa" / "app" / "services.xml"
    services.parent.mkdir(parents=True)
    services.write_text(SERVICES_TEMPLATE.format(stemmer="snowballPorter", nodes=2))

    stopwords = tmp_path / "vespa" / "app" / "lucene-linguistics" / "en" / "stopwords.txt"
    stopwords.parent.mkdir(parents=True)
    stopwords.write_text("the\na\n")

    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _run(repo: Path, base: str = "main") -> str:
    result = subprocess.run(
        ["python3", str(SCRIPT_PATH), base],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_stemmer_change_is_detected(repo: Path) -> None:
    """Swapping the stemmer changes indexed tokens, so it must be flagged."""
    _git(repo, "checkout", "-b", "feature")
    (repo / "vespa" / "app" / "services.xml").write_text(
        SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2)
    )
    _git(repo, "commit", "-am", "swap stemmer")

    out = _run(repo)
    assert "changed=true" in out
    assert "LuceneLinguistics component" in out


def test_unrelated_services_change_is_ignored(repo: Path) -> None:
    """Node counts etc. live in services.xml but don't affect indexed tokens."""
    _git(repo, "checkout", "-b", "feature")
    (repo / "vespa" / "app" / "services.xml").write_text(
        SERVICES_TEMPLATE.format(stemmer="snowballPorter", nodes=4)
    )
    _git(repo, "commit", "-am", "scale up nodes")

    out = _run(repo)
    assert "changed=false" in out


def test_stopwords_change_is_detected(repo: Path) -> None:
    """stopwords.txt is read via configDir, so editing it changes tokenisation."""
    _git(repo, "checkout", "-b", "feature")
    stopwords = repo / "vespa" / "app" / "lucene-linguistics" / "en" / "stopwords.txt"
    stopwords.write_text("the\na\nand\n")
    _git(repo, "commit", "-am", "add stopword")

    out = _run(repo)
    assert "changed=true" in out
    assert "stopwords.txt" in out


def test_readme_change_is_ignored(repo: Path) -> None:
    """Prose in the linguistics dir doesn't affect indexing."""
    _git(repo, "checkout", "-b", "feature")
    readme = repo / "vespa" / "app" / "lucene-linguistics" / "README.md"
    readme.write_text("# Docs\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "document things")

    out = _run(repo)
    assert "changed=false" in out


def test_no_change_at_all(repo: Path) -> None:
    _git(repo, "checkout", "-b", "feature")
    (repo / "unrelated.txt").write_text("hello\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "unrelated")

    out = _run(repo)
    assert "changed=false" in out


def test_missing_component_raises(script) -> None:
    """A renamed or removed component must not silently compare equal."""
    with pytest.raises(script.LinguisticsNotFound):
        script.extract_linguistics("<services version='1.0'></services>")


def test_unparsable_xml_raises(script) -> None:
    with pytest.raises(script.LinguisticsNotFound):
        script.extract_linguistics("<services><unclosed>")


def test_duplicate_components_raise(script) -> None:
    """Two matching components means we can't tell which one is live."""
    doubled = SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2).replace(
        "</container>",
        SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2)
        .split("<container id=\"default\" version=\"1.0\">")[1]
        .split("<nodes")[0]
        + "</container>",
    )
    with pytest.raises(script.LinguisticsNotFound):
        script.extract_linguistics(doubled)


def test_reformatting_is_not_a_change(script) -> None:
    """Whitespace and attribute order must not look like a config change."""
    a = script.extract_linguistics(
        SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2)
    )
    reformatted = SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2).replace(
        "<name>kStem</name>", "<name>  kStem  </name>"
    )
    assert script.extract_linguistics(reformatted) == a


def test_renamed_component_is_reported_as_changed(repo: Path) -> None:
    """Fail closed: if we can't find the component, warn rather than pass."""
    _git(repo, "checkout", "-b", "feature")
    services = repo / "vespa" / "app" / "services.xml"
    services.write_text(
        SERVICES_TEMPLATE.format(stemmer="kStem", nodes=2).replace(
            "com.yahoo.language.lucene.LuceneLinguistics", "com.example.Something"
        )
    )
    _git(repo, "commit", "-am", "rename component")

    out = _run(repo)
    assert "changed=true" in out
    assert "could not compare" in out
