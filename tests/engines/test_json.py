"""Tests specific to JSON implementation."""

import pytest

from search import Primitive
from search.document import Document
from search.engines.json import (
    DEFAULT_SPLIT_TOKEN,
    JSONDocumentSearchEngine,
    JSONDocumentSearchSchema,
    JSONLabelSearchSchema,
    JSONSearchEngine,
    JSONSearchSchema,
    deserialise_pydantic_list_from_jsonl,
    serialise_pydantic_list_as_jsonl,
)
from search.label import Label
from search.passage import Passage


def test_whether_schemas_build_an_appropriate_searchable_string(
    search_schema: JSONSearchSchema,
    test_documents: list[Document],
    test_passages: list[Passage],
    test_labels: list[Label],
):
    items: list[Primitive] = []
    if search_schema.model_class == Document:
        items = test_documents
    elif search_schema.model_class == Passage:
        items = test_passages
    elif search_schema.model_class == Label:
        items = test_labels
    else:
        pytest.fail("Unknown model class")

    for item in items:
        components = search_schema.extract_searchable_components(item)
        searchable_string = search_schema.build_searchable_string(item)

        # All of the components should be in the searchable string
        for component in components:
            assert component.lower() in searchable_string

        # The searchable string should contain the split token if there are multiple
        # components
        if len(components) > 1:
            assert DEFAULT_SPLIT_TOKEN in searchable_string


def test_whether_split_token_prevents_cross_field_matches():
    # Create a Document where the last word of the title + first word of the description
    # would match if not separated
    doc = Document(
        title="A B",
        source_url="https://example.com",
        description="C D",
        original_document_id="test",
    )

    searchable_string = JSONDocumentSearchSchema().build_searchable_string(doc)

    # The searchable_string should be "a b <SPLIT> c d"
    # "b c" should NOT match (false positive without split token)
    assert "b c" not in searchable_string
    assert f"b {DEFAULT_SPLIT_TOKEN} c" in searchable_string


def test_whether_engine_initialization_with_items_inserts_correct_number_of_items(
    test_documents: list[Document],
):
    engine = JSONDocumentSearchEngine(items=test_documents)
    assert len(engine.items) == len(test_documents)


def test_whether_engine_initialization_with_empty_items_results_in_an_empty_engine():
    engine = JSONDocumentSearchEngine(items=[])
    assert len(engine.items) == 0
    assert engine.search("") == []


def test_whether_serialisation_and_deserialisation_round_trip_correctly(
    test_items: list[Primitive],
):
    """Verify serialization and deserialization preserve Document data."""
    model_class = test_items[0].__class__
    jsonl = serialise_pydantic_list_as_jsonl(test_items)
    recovered = deserialise_pydantic_list_from_jsonl(jsonl, model_class)

    assert len(recovered) == len(test_items)
    for original, recovered_item in zip(test_items, recovered):
        assert recovered_item == original


def test_whether_schema_extracts_all_relevant_fields(
    search_schema: JSONSearchSchema,
    test_documents: list[Document],
    test_passages: list[Passage],
    test_labels: list[Label],
):
    """Verify schema extracts all expected searchable components."""
    # Get appropriate test items based on schema type
    test_items: list[Primitive] = []
    if search_schema.model_class == Document:
        test_items = test_documents
    elif search_schema.model_class == Passage:
        test_items = test_passages
    elif search_schema.model_class == Label:
        test_items = test_labels
    else:
        pytest.fail("Unknown model class")

    for item in test_items:
        fields = search_schema.extract_searchable_components(item)

        # Verify fields are extracted (non-empty list)
        assert isinstance(fields, list)
        assert len(fields) > 0

        # Verify all fields are strings
        assert all(isinstance(field, str) for field in fields)

        # Verify searchable string can be built from extracted fields
        searchable_string = search_schema.build_searchable_string(item)
        assert isinstance(searchable_string, str)
        assert len(searchable_string) > 0


def test_whether_alternative_labels_are_sorted_by_schema(
    json_label_search_schema: JSONLabelSearchSchema,
):
    """Verify alternative labels are sorted in searchable components."""
    label = Label(
        preferred_label="test",
        alternative_labels=["z", "a", "m"],
        negative_labels=[],
    )

    fields = json_label_search_schema.extract_searchable_components(label)

    alt_label_fields = fields[1:-1]  # Between preferred and description
    assert alt_label_fields == ["a", "m", "z"]  # Sorted alphabetically


def test_whether_engine_can_initialize_from_file_path(
    tmp_path,
    any_json_engine: JSONSearchEngine,
    test_documents: list[Document],
    test_passages: list[Passage],
    test_labels: list[Label],
):
    """
    Verify that an engine can be initialised from a JSONL file.

    We do this by serializing test data to a JSONL file, then initializing
    a new engine from that file to verify that it loads and performs searches.
    """
    file_path = tmp_path / "test.jsonl"

    # Get appropriate test items based on engine type
    items: list[Primitive] = []
    if any_json_engine.schema.model_class == Document:
        items = test_documents
    elif any_json_engine.schema.model_class == Passage:
        items = test_passages
    elif any_json_engine.schema.model_class == Label:
        items = test_labels
    else:
        pytest.fail("Unknown model class")

    # Serialize the items as JSON and write them to a file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(serialise_pydantic_list_as_jsonl(items))

    # Initialize new engine from file
    engine_class = any_json_engine.__class__
    new_engine = engine_class(file_path=file_path)

    # Verify engine loaded all items
    assert len(new_engine.items) == len(items)

    # Get a valid search term from the test items
    search_term: str = ""
    if any_json_engine.schema.model_class == Document:
        search_term = test_documents[0].title
    elif any_json_engine.schema.model_class == Passage:
        search_term = test_passages[0].text
    elif any_json_engine.schema.model_class == Label:
        search_term = test_labels[0].preferred_label
    else:
        pytest.fail("Unknown model class")

    # Verify search works
    results = new_engine.search(search_term)
    assert len(results) >= 1
    assert all(isinstance(r, any_json_engine.schema.model_class) for r in results)


def test_whether_engine_handles_empty_jsonl_file(tmp_path):
    """Verify engine can handle empty JSONL file."""
    file_path = tmp_path / "empty.jsonl"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("")

    engine = JSONDocumentSearchEngine(file_path=file_path)
    assert len(engine.items) == 0
    results = engine.search("")
    assert results == []


def test_whether_engine_handles_jsonl_with_empty_lines(
    tmp_path, test_documents: list[Document]
):
    """Verify engine skips empty lines in JSONL file."""
    file_path = tmp_path / "with_empty_lines.jsonl"
    jsonl = serialise_pydantic_list_as_jsonl(test_documents)
    # Add empty lines
    jsonl_with_blanks = "\n".join([jsonl, "", jsonl.split("\n")[0], ""])
    file_path.write_text(jsonl_with_blanks, encoding="utf-8")

    engine = JSONDocumentSearchEngine(file_path=file_path)
    # Should load all documents plus one duplicate from the extra line
    assert len(engine.items) == len(test_documents) + 1
