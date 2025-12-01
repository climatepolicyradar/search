from knowledge_graph.identifiers import Identifier
from pydantic import AnyHttpUrl, BaseModel, Field, computed_field


class Document(BaseModel):
    """Base class for a CPR document"""

    title: str = Field(description="The title of the document")
    source_url: AnyHttpUrl = Field(
        description="The URL where the original document can be found"
    )
    description: str = Field(description="A description or summary of the document")
    original_document_id: str = Field(
        description=(
            "The original ID of the document from the source system, "
            "e.g. a document's ID in the main CPR apps"
        )
    )
    labels: list[Identifier] = Field(
        default=[],
        description=(
            "List of identifiers of labels which are associated with this "
            "document, eg metadata like geography, sector, etc."
        ),
    )

    @computed_field
    @property
    def id(self) -> Identifier:
        """A canonical identifier for the document"""
        return Identifier.generate(self.title, self.source_url)

    @classmethod
    def from_huggingface_row(cls, row: dict) -> "Document":
        """Create a Document object from a row of a HuggingFace dataset"""
        title = (
            row.get("document_metadata.document_title") or row.get("document_id") or ""
        )
        source_url = row["document_metadata.source_url"]
        description = row.get("document_metadata.description", "")
        original_document_id = row.get("document_id", "")
        return cls(
            title=title,
            source_url=source_url,
            description=description,
            original_document_id=original_document_id,
            labels=[],  # deliberately leaving this empty for now
        )
