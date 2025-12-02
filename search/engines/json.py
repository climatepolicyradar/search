from pathlib import Path
from typing import Any, Generic, Sequence, TypeVar

from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel

from search.document import Document
from search.engines import (
    DocumentSearchEngine,
    LabelSearchEngine,
    PassageSearchEngine,
    SearchEngine,
)
from search.label import Label
from search.passage import Passage

TModel = TypeVar("TModel", Label, Passage, Document)


def serialise_pydantic_list_as_jsonl[T: BaseModel](models: Sequence[T]) -> str:
    """
    Serialize a list of Pydantic models as JSONL (JSON Lines) format.

    Each model is serialized on a separate line using model_dump_json().
    """
    jsonl_content = "\n".join(model.model_dump_json() for model in models)

    return jsonl_content


def deserialise_pydantic_list_from_jsonl[T: BaseModel](
    jsonl_content: str, model_class: type[T]
) -> list[T]:
    """
    Deserialize a JSONL (JSON Lines) string into a list of Pydantic models.

    Each line is parsed as JSON and validated into an instance of the given model class.
    Empty lines are skipped.
    """
    models = []
    for line in jsonl_content.strip().split("\n"):
        if line.strip():  # Skip empty lines
            models.append(model_class.model_validate_json(line))
    return models


class JSONSearchEngine(SearchEngine, Generic[TModel]):
    """A search engine that searches for primitives in a JSONL file."""

    model_class: type[BaseModel] | None = None

    def __init__(self, file_path: str | Path, model_class: type[TModel] | None = None):
        """Initialize the JSON search engine."""
        if model_class is None:
            if self.model_class is None:
                raise ValueError(
                    "model_class must be provided either as argument or class attribute"
                )
            model_class = self.model_class

        with open(file_path, "r", encoding="utf-8") as f:
            self.items = deserialise_pydantic_list_from_jsonl(f.read(), model_class)

    @staticmethod
    def _build_searchable_string(
        components: Sequence[Any], split_token: str = " <SPLIT> "
    ) -> str:
        """
        Build a normalized searchable string for a given sequence of components.

        Combines the components into a single lowercase string for efficient searching.
        A split token is inserted between each component to prevent false matches across
        boundaries.

        For example given the components ["a b", "c d", "e f", "g h"], the searchable
        string would be:
            "a b <SPLIT> c d <SPLIT> e f <SPLIT> g h"
        Without including the split token, concatenating with just spaces as
        "a b c d e f g h" would incorrectly match a search for "b c", even though
        that phrase doesn't actually appear in any single component. The split token
        prevents such inadvertent matches across component boundaries.
        """
        return split_token.join(str(component) for component in components).lower()


class JSONLabelSearchEngine(JSONSearchEngine[Label], LabelSearchEngine):
    """A search engine that searches for labels in a JSONL file."""

    model_class = Label

    def __init__(self, file_path: str | Path):
        """Initialize the JSON label search engine."""
        super().__init__(file_path)

        self.id_to_searchable_strings: dict[Identifier, str] = {
            label.id: self._build_searchable_string(
                [
                    label.preferred_label,
                    *sorted(label.alternative_labels),
                    label.description,
                ]
            )
            for label in self.items
        }

    def search(self, terms: str) -> list[Label]:
        """Search for labels in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            label
            for label in self.items
            if lowercased_terms in self.id_to_searchable_strings[label.id]
        ]


class JSONPassageSearchEngine(JSONSearchEngine[Passage], PassageSearchEngine):
    """A search engine that searches for passages in a JSONL file."""

    model_class = Passage

    def search(self, terms: str) -> list[Passage]:
        """Search for passages in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            passage
            for passage in self.items
            if lowercased_terms in passage.text.lower()
        ]


class JSONDocumentSearchEngine(JSONSearchEngine[Document], DocumentSearchEngine):
    """A search engine that searches for documents in a JSONL file."""

    model_class = Document

    def __init__(self, file_path: str | Path):
        """Initialize the JSON document search engine."""
        super().__init__(file_path)
        self.id_to_searchable_strings: dict[Identifier, str] = {
            document.id: self._build_searchable_string(
                [document.title, document.description]
            )
            for document in self.items
        }

    def search(self, terms: str) -> list[Document]:
        """Search for documents in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            document
            for document in self.items
            if lowercased_terms in self.id_to_searchable_strings[document.id]
        ]
