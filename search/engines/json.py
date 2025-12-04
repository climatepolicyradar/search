from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, Sequence, TypeVar, overload

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
DEFAULT_SPLIT_TOKEN = "<SPLIT>"


def serialise_pydantic_list_as_jsonl[T: BaseModel](models: Sequence[T]) -> str:
    """
    Serialise a list of Pydantic models as JSONL (JSON Lines) format.

    Each model is serialised on a separate line using model_dump_json().
    """
    return "\n".join(model.model_dump_json() for model in models)


def deserialise_pydantic_list_from_jsonl[T: BaseModel](
    jsonl_content: str, model_class: type[T]
) -> list[T]:
    """
    Deserialise a JSONL (JSON Lines) string into a list of Pydantic models.

    Each line is parsed as JSON and validated into an instance of the given model class.
    Empty lines are skipped.
    """
    models = []
    for line in jsonl_content.strip().split("\n"):
        if line.strip():
            models.append(model_class.model_validate_json(line))
    return models


@dataclass(frozen=True)
class JSONSearchSchema(Generic[TModel]):
    """Schema defining how to search a model."""

    model_class: type[TModel]
    extract_searchable_components: Callable[[TModel], list[str]]

    def build_searchable_string(
        self, item: TModel, split_token: str = DEFAULT_SPLIT_TOKEN
    ) -> str:
        """
        Build a normalised searchable string for an item.

        Combines search fields into a single lowercase string. A split token
        prevents false matches across component boundaries.

        Example: ["a b", "c d"] -> "a b <SPLIT> c d"
        Without the split token, "b c" would incorrectly match.
        """
        components = self.extract_searchable_components(item)
        split_token_with_surrounding_spaces = f" {split_token} "
        return split_token_with_surrounding_spaces.join(
            str(component).lower() for component in components
        )


class JSONDocumentSearchSchema(JSONSearchSchema[Document]):
    """Schema definition for a document search engine."""

    def __init__(self):
        super().__init__(
            model_class=Document,
            extract_searchable_components=lambda doc: [doc.title, doc.description],
        )


class JSONPassageSearchSchema(JSONSearchSchema[Passage]):
    """Schema definition for a passage search engine."""

    def __init__(self):
        super().__init__(
            model_class=Passage,
            extract_searchable_components=lambda passage: [passage.text],
        )


class JSONLabelSearchSchema(JSONSearchSchema[Label]):
    """Schema definition for a label search engine."""

    def __init__(self):
        super().__init__(
            model_class=Label,
            extract_searchable_components=lambda label: [
                label.preferred_label,
                *sorted(label.alternative_labels),
                label.description or "",
            ],
        )


class JSONSearchEngine(SearchEngine, Generic[TModel]):
    """Base search engine using in-memory search over JSONL data."""

    schema: JSONSearchSchema[TModel]

    @overload
    def __init__(self, *, file_path: str | Path) -> None: ...

    @overload
    def __init__(self, *, items: Iterable[TModel]) -> None: ...

    def __init__(
        self,
        *,
        file_path: str | Path | None = None,
        items: Iterable[TModel] | None = None,
    ) -> None:
        """
        Initialise the JSON search engine.

        Can be called in two ways:
        1. JSONSearchEngine(file_path=...) - use existing JSONL file
        2. JSONSearchEngine(items=...) - create from items
        """
        if file_path is None and items is None:
            raise ValueError("Either file_path or items must be provided")
        if file_path is not None and items is not None:
            raise ValueError("Only one of file_path or items must be provided")

        if file_path is not None:
            with open(file_path, "r", encoding="utf-8") as f:
                self.items = deserialise_pydantic_list_from_jsonl(
                    f.read(), self.schema.model_class
                )
        else:
            self.items = list(items)

        # Build search index
        self._searchable_strings: dict[Identifier, str] = {
            item.id: self.schema.build_searchable_string(item) for item in self.items
        }

    def search(self, terms: str) -> list[TModel]:
        """Search for items matching the terms (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            item
            for item in self.items
            if lowercased_terms in self._searchable_strings[item.id]
        ]


class JSONDocumentSearchEngine(JSONSearchEngine[Document], DocumentSearchEngine):
    """Search engine for documents using JSONL."""

    schema = JSONDocumentSearchSchema()


class JSONPassageSearchEngine(JSONSearchEngine[Passage], PassageSearchEngine):
    """Search engine for passages using JSONL."""

    schema = JSONPassageSearchSchema()


class JSONLabelSearchEngine(JSONSearchEngine[Label], LabelSearchEngine):
    """Search engine for labels using JSONL."""

    schema = JSONLabelSearchSchema()
