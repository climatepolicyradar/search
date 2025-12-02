"""Tests for search engines focusing on functional correctness."""

import pytest

from search.document import Document
from search.engines import SearchEngine
from search.engines.duckdb import (
    DuckDBDocumentSearchEngine,
    DuckDBLabelSearchEngine,
    DuckDBPassageSearchEngine,
    create_documents_duckdb_table,
    create_labels_duckdb_table,
    create_passages_duckdb_table,
)
from search.engines.json import (
    JSONDocumentSearchEngine,
    JSONLabelSearchEngine,
    JSONPassageSearchEngine,
    serialise_pydantic_list_as_jsonl,
)
from search.label import Label
from search.passage import Passage


# Fixtures for temporary file/database creation
@pytest.fixture
def jsonl_labels_file(tmp_path, test_labels):
    """Create a temporary JSONL file with labels."""
    file_path = tmp_path / "labels.jsonl"
    jsonl_content = serialise_pydantic_list_as_jsonl(test_labels)
    file_path.write_text(jsonl_content, encoding="utf-8")
    return file_path


@pytest.fixture
def jsonl_documents_file(tmp_path, test_documents):
    """Create a temporary JSONL file with documents."""
    file_path = tmp_path / "documents.jsonl"
    jsonl_content = serialise_pydantic_list_as_jsonl(test_documents)
    file_path.write_text(jsonl_content, encoding="utf-8")
    return file_path


@pytest.fixture
def jsonl_passages_file(tmp_path, test_passages):
    """Create a temporary JSONL file with passages."""
    file_path = tmp_path / "passages.jsonl"
    jsonl_content = serialise_pydantic_list_as_jsonl(test_passages)
    file_path.write_text(jsonl_content, encoding="utf-8")
    return file_path


@pytest.fixture
def duckdb_labels_db(tmp_path, test_labels):
    """Create a temporary DuckDB database with labels."""
    db_path = tmp_path / "labels.duckdb"
    create_labels_duckdb_table(db_path, test_labels)
    return db_path


@pytest.fixture
def duckdb_documents_db(tmp_path, test_documents):
    """Create a temporary DuckDB database with documents."""
    db_path = tmp_path / "documents.duckdb"
    create_documents_duckdb_table(db_path, test_documents)
    return db_path


@pytest.fixture
def duckdb_passages_db(tmp_path, test_passages):
    """Create a temporary DuckDB database with passages."""
    db_path = tmp_path / "passages.duckdb"
    create_passages_duckdb_table(db_path, test_passages)
    return db_path


# Engine instance fixtures
@pytest.fixture
def json_label_engine(jsonl_labels_file):
    """Create a JSON label search engine instance."""
    return JSONLabelSearchEngine(jsonl_labels_file)


@pytest.fixture
def json_document_engine(jsonl_documents_file):
    """Create a JSON document search engine instance."""
    return JSONDocumentSearchEngine(jsonl_documents_file)


@pytest.fixture
def json_passage_engine(jsonl_passages_file):
    """Create a JSON passage search engine instance."""
    return JSONPassageSearchEngine(jsonl_passages_file)


@pytest.fixture
def duckdb_label_engine(duckdb_labels_db):
    """Create a DuckDB label search engine instance."""
    return DuckDBLabelSearchEngine(duckdb_labels_db)


@pytest.fixture
def duckdb_document_engine(duckdb_documents_db):
    """Create a DuckDB document search engine instance."""
    return DuckDBDocumentSearchEngine(duckdb_documents_db)


@pytest.fixture
def duckdb_passage_engine(duckdb_passages_db):
    """Create a DuckDB passage search engine instance."""
    return DuckDBPassageSearchEngine(duckdb_passages_db)


@pytest.fixture(
    params=[
        "json_label_engine",
        "duckdb_label_engine",
        "json_document_engine",
        "duckdb_document_engine",
        "json_passage_engine",
        "duckdb_passage_engine",
    ]
)
def engine(request: pytest.FixtureRequest) -> SearchEngine:
    """Parametrized fixture providing all engine types."""
    return request.getfixturevalue(request.param)


def get_valid_search_term(
    engine: SearchEngine,
    test_documents: list[Document],
    test_labels: list[Label],
    test_passages: list[Passage],
) -> str:
    """
    Get a valid search term for a given engine

    The search term is chosen based on the engine's model class and the test data
    fixtures. For example, if the supplied engine is a based on Documents, the search
    term is the title of the first document in the test data fixtures.
    """
    expected_type = engine.model_class

    if expected_type == Document:
        return test_documents[0].title
    elif expected_type == Label:
        return test_labels[0].preferred_label
    elif expected_type == Passage:
        return test_passages[0].text
    else:
        raise ValueError(f"Unknown engine model class: {expected_type}")


def get_non_matching_search_term() -> str:
    """
    Get a search term that is guaranteed not to match any test data.

    Returns a fixed string that is unlikely to appear in Hypothesis-generated test data.
    """
    return "xyzabc123nonexistent"


def test_whether_engine_can_be_initialized_with_valid_data_file(engine):
    assert engine is not None


def test_whether_engine_returns_correct_result_types(engine: SearchEngine):
    expected_type = engine.model_class
    results = engine.search("test")
    assert isinstance(results, list)
    assert all(isinstance(result, expected_type) for result in results)


def test_whether_engine_returns_correct_types_when_searching_with_valid_term(
    engine: SearchEngine, test_documents, test_labels, test_passages
):
    expected_type = engine.model_class
    search_terms = get_valid_search_term(
        engine, test_documents, test_labels, test_passages
    )
    results = engine.search(search_terms)
    assert isinstance(results, list)
    assert all(isinstance(result, expected_type) for result in results)


def test_whether_engine_returns_list_when_no_matches(engine: SearchEngine):
    search_terms = get_non_matching_search_term()
    results = engine.search(search_terms)
    assert isinstance(results, list)
    assert len(results) == 0


def test_whether_engine_handles_empty_search_terms(engine: SearchEngine):
    results = engine.search("")
    assert isinstance(results, list)
    assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_handles_special_characters_in_search_terms(
    engine: SearchEngine,
):
    special_chars = ["'", '"', "%", "_", "\\", "/", "(", ")", "[", "]"]
    for char in special_chars:
        results = engine.search(f"test{char}term")
        assert isinstance(results, list)
        assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_search_always_returns_list(engine: SearchEngine):
    results = engine.search("any string input")
    assert isinstance(results, list)


def test_whether_engine_handles_very_long_search_terms(engine: SearchEngine):
    long_term = "a" * 10000
    results = engine.search(long_term)
    assert isinstance(results, list)
    assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_handles_unicode_characters_in_search_terms(
    engine: SearchEngine,
):
    unicode_terms = ["🚀", "café", "北京", "🎉🎊🎈", "test🚀term"]
    for term in unicode_terms:
        results = engine.search(term)
        assert isinstance(results, list)
        assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_handles_whitespace_only_search_terms(engine: SearchEngine):
    whitespace_terms = [" ", "\t", "\n", "   ", "\t\n", " \t \n "]
    for term in whitespace_terms:
        results = engine.search(term)
        assert isinstance(results, list)
        assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_handles_numeric_search_terms(engine: SearchEngine):
    numeric_terms = ["123", "0", "999999", "3.14", "-42"]
    for term in numeric_terms:
        results = engine.search(term)
        assert isinstance(results, list)
        assert all(isinstance(result, engine.model_class) for result in results)


def test_whether_engine_returns_items_with_required_fields(
    engine: SearchEngine, test_documents, test_labels, test_passages
):
    search_term = get_valid_search_term(
        engine, test_documents, test_labels, test_passages
    )
    results = engine.search(search_term)
    for result in results:
        assert hasattr(result, "id")
        assert result.id is not None


def test_whether_engine_preserves_item_ids(
    engine: SearchEngine, test_documents, test_labels, test_passages
):
    search_term = get_valid_search_term(
        engine, test_documents, test_labels, test_passages
    )
    results1 = engine.search(search_term)
    results2 = engine.search(search_term)
    ids1 = {result.id for result in results1}
    ids2 = {result.id for result in results2}
    assert ids1 == ids2


def test_whether_engine_returns_valid_model_instances(
    engine: SearchEngine, test_documents, test_labels, test_passages
):
    search_term = get_valid_search_term(
        engine, test_documents, test_labels, test_passages
    )
    results = engine.search(search_term)
    for result in results:
        assert isinstance(result, engine.model_class)
        model_dict = result.model_dump()
        assert isinstance(model_dict, dict)
        assert "id" in model_dict


def test_whether_engine_model_class_attribute_is_set(engine: SearchEngine):
    assert engine.model_class is not None
    assert isinstance(engine.model_class, type)


def test_whether_engine_model_class_matches_search_return_type(engine: SearchEngine):
    results = engine.search("test")
    if results:
        assert isinstance(results[0], engine.model_class)


def test_whether_engine_results_can_be_used_as_model_instances(
    engine: SearchEngine, test_documents, test_labels, test_passages
):
    search_term = get_valid_search_term(
        engine, test_documents, test_labels, test_passages
    )
    results = engine.search(search_term)
    for result in results:
        assert hasattr(result, "model_dump")
        assert hasattr(result, "model_copy")
        dumped = result.model_dump()
        assert isinstance(dumped, dict)


def test_whether_duckdb_engine_handles_sql_injection_attempts(
    duckdb_label_engine: DuckDBLabelSearchEngine,
):
    engine = duckdb_label_engine
    injection_attempts = [
        "'; DROP TABLE labels; --",
        "' OR '1'='1",
        "'; SELECT * FROM labels; --",
        "test'term",
    ]
    for attempt in injection_attempts:
        results = engine.search(attempt)
        assert isinstance(results, list)
        assert all(isinstance(result, engine.model_class) for result in results)


@pytest.fixture
def empty_jsonl_file(tmp_path):
    """Create an empty JSONL file."""
    file_path = tmp_path / "empty.jsonl"
    file_path.write_text("", encoding="utf-8")
    return file_path


@pytest.fixture
def empty_duckdb_db(tmp_path):
    """Create an empty DuckDB database."""
    db_path = tmp_path / "empty.duckdb"
    create_labels_duckdb_table(db_path, [])
    return db_path


def test_whether_engine_initializes_with_empty_data(empty_jsonl_file, empty_duckdb_db):
    json_engine = JSONLabelSearchEngine(empty_jsonl_file)
    assert json_engine is not None
    results = json_engine.search("test")
    assert isinstance(results, list)
    assert len(results) == 0

    duckdb_engine = DuckDBLabelSearchEngine(empty_duckdb_db)
    assert duckdb_engine is not None
    results = duckdb_engine.search("test")
    assert isinstance(results, list)
    assert len(results) == 0


@pytest.fixture
def single_label_jsonl_file(tmp_path, test_labels):
    """Create a JSONL file with a single label."""
    file_path = tmp_path / "single_label.jsonl"
    single_label = [test_labels[0]]
    jsonl_content = serialise_pydantic_list_as_jsonl(single_label)
    file_path.write_text(jsonl_content, encoding="utf-8")
    return file_path


@pytest.fixture
def single_label_duckdb_db(tmp_path, test_labels):
    """Create a DuckDB database with a single label."""
    db_path = tmp_path / "single_label.duckdb"
    single_label = [test_labels[0]]
    create_labels_duckdb_table(db_path, single_label)
    return db_path


def test_whether_engine_initializes_with_single_item(
    single_label_jsonl_file, single_label_duckdb_db, test_labels
):
    json_engine = JSONLabelSearchEngine(single_label_jsonl_file)
    assert json_engine is not None
    search_term = get_valid_search_term(json_engine, [], [test_labels[0]], [])
    results = json_engine.search(search_term)
    assert isinstance(results, list)
    assert len(results) == 1
    assert all(isinstance(result, Label) for result in results)

    duckdb_engine = DuckDBLabelSearchEngine(single_label_duckdb_db)
    assert duckdb_engine is not None
    search_term = get_valid_search_term(duckdb_engine, [], [test_labels[0]], [])
    results = duckdb_engine.search(search_term)
    assert isinstance(results, list)
    assert len(results) == 1
    assert all(isinstance(result, Label) for result in results)


@pytest.fixture
def many_labels_jsonl_file(tmp_path, test_labels):
    """Create a JSONL file with many labels by duplicating test data."""
    file_path = tmp_path / "many_labels.jsonl"
    many_labels = test_labels * 20
    jsonl_content = serialise_pydantic_list_as_jsonl(many_labels)
    file_path.write_text(jsonl_content, encoding="utf-8")
    return file_path


@pytest.fixture
def many_labels_duckdb_db(tmp_path, test_labels):
    """Create a DuckDB database with many labels by duplicating test data."""
    db_path = tmp_path / "many_labels.duckdb"
    many_labels = test_labels * 20
    create_labels_duckdb_table(db_path, many_labels)
    return db_path


def test_whether_engine_initializes_with_many_items(
    many_labels_jsonl_file, many_labels_duckdb_db, test_labels
):
    json_engine = JSONLabelSearchEngine(many_labels_jsonl_file)
    assert json_engine is not None
    search_term = get_valid_search_term(json_engine, [], test_labels, [])
    results = json_engine.search(search_term)

    assert isinstance(results, list)
    assert all(isinstance(result, Label) for result in results)

    duckdb_engine = DuckDBLabelSearchEngine(many_labels_duckdb_db)
    assert duckdb_engine is not None
    search_term = get_valid_search_term(duckdb_engine, [], test_labels, [])
    results = duckdb_engine.search(search_term)
    assert isinstance(results, list)
    assert all(isinstance(result, Label) for result in results)
