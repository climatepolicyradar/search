from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, Field, computed_field

from search.label import Label


class Passage(BaseModel):
    """Base class for a passage"""

    text: str = Field(description="The text content of the passage")
    document_id: Identifier = Field(
        description="Canonical ID for the document this passage belongs to"
    )
    labels: list[Label] = Field(
        description=(
            "List of which are associated with this passage, "
            "eg topics identified by our classifiers"
        ),
    )
    original_passage_id: str = Field(
        description=(
            "The original ID of the passage from the source system, "
            "e.g. a passage's ID in the main CPR apps"
        )
    )

    @computed_field
    @property
    def id(self) -> Identifier:
        """A canonical identifier for the passage"""
        return Identifier.generate(self.text, self.document_id)
