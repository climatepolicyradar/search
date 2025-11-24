from pydantic import AnyHttpUrl, BaseModel, computed_field

from search.identifier import Identifier
from search.label import Label


class Document(BaseModel):
    """Base class for a CPR document"""

    title: str
    source_url: AnyHttpUrl
    description: str
    labels: list[Label] = []

    @computed_field
    @property
    def id(self) -> Identifier:
        """Return a unique ID for the document"""
        return Identifier.generate(self.title, self.source_url)
