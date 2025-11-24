from pydantic import BaseModel, computed_field

from search.identifier import Identifier
from search.label import Label


class Passage(BaseModel):
    """Base class for a passage"""

    text: str
    document_id: Identifier
    labels: list[Label]

    @computed_field
    @property
    def id(self) -> Identifier:
        """Return a unique ID for the passage"""
        return Identifier.generate(self.text, self.document_id)
