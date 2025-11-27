from knowledge_graph.identifiers import Identifier
from pydantic import AnyHttpUrl, BaseModel, Field, computed_field

from search.label import Label


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
    labels: list[Label] = Field(
        default=[],
        description="List of which are associated with this document, eg metadata like geography, sector, etc.",
    )

    @computed_field
    @property
    def id(self) -> Identifier:
        """A canonical identifier for the document"""
        return Identifier.generate(self.title, self.source_url)
