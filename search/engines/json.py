from search.document import Document
from search.engines import DocumentSearchEngine, LabelSearchEngine, PassageSearchEngine
from search.identifier import Identifier
from search.label import Label
from search.passage import Passage


class JSONLabelSearchEngine(LabelSearchEngine):
    """A search engine that searches for labels in a JSONL file."""

    def __init__(self, file_path: str):
        """Initialize the JSON label search engine."""
        with open(file_path, "r", encoding="utf-8") as f:
            self.labels = [
                Label.model_validate_json(line) for line in f if line.strip()
            ]

        # Build lookup dictionaries for efficient searching
        self.id_to_label: dict[Identifier, Label] = {
            label.id: label for label in self.labels
        }
        self.searchable_strings: dict[Identifier, str] = {
            label.id: self._build_searchable_string(label) for label in self.labels
        }

    @staticmethod
    def _build_searchable_string(label: Label, split_token: str = " <SPLIT> ") -> str:
        """Build a normalized searchable string from a label."""
        return split_token.join(
            [
                label.preferred_label,
                *sorted(label.alternative_labels),
                label.description,
            ]
        ).lower()

    def search(self, terms: str) -> list[Label]:
        """Search for labels in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            self.id_to_label[identifier]
            for identifier, searchable_string in self.searchable_strings.items()
            if lowercased_terms in searchable_string
        ]


class JSONPassageSearchEngine(PassageSearchEngine):
    """A search engine that searches for passages in a JSONL file."""

    def __init__(self, file_path: str):
        """Initialize the JSON passage search engine."""
        with open(file_path, "r", encoding="utf-8") as f:
            self.passages = [
                Passage.model_validate_json(line) for line in f if line.strip()
            ]

    def search(self, terms: str) -> list[Passage]:
        """Search for passages in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            passage
            for passage in self.passages
            if lowercased_terms in passage.text.lower()
        ]


class JSONDocumentSearchEngine(DocumentSearchEngine):
    """A search engine that searches for documents in a JSONL file."""

    def __init__(self, file_path: str):
        """Initialize the JSON document search engine."""
        with open(file_path, "r", encoding="utf-8") as f:
            self.documents = [
                Document.model_validate_json(line) for line in f if line.strip()
            ]

    def search(self, terms: str) -> list[Document]:
        """Search for documents in the JSONL file (case-insensitive)."""
        lowercased_terms = terms.lower()
        return [
            document
            for document in self.documents
            if lowercased_terms in document.title.lower()
            or lowercased_terms in document.description.lower()
        ]
