from pydantic import AnyHttpUrl, BaseModel, computed_field

from search.identifier import Identifier
from search.label import Label
from search.passage import Passage


class Document(BaseModel):
    """Base class for a CPR document"""

    title: str
    source_url: AnyHttpUrl
    labels: list[Label]
    passages: list[Passage]

    @computed_field
    @property
    def id(self) -> Identifier:
        """Return a unique ID for the document"""
        return Identifier.generate(self.title, self.source_url)
