from pydantic import BaseModel, Field

from search.data_in_models import Label as DataInLabel
from search.data_in_models import LabelRelationship


class Label(BaseModel):
    """Base class for a label"""

    id: str = Field(default="")
    type: str = Field(default="")
    value: str = Field(default="")
    alternative_labels: list[str] = Field(default=[])
    subconcept_labels: list[str] = Field(default=[])
    description: str = Field(default="")
    negative_labels: list[str] = Field(default=[])

    @property
    def all_labels(self) -> list[str]:
        """Value + alternative labels"""

        return [self.value] + self.alternative_labels + self.subconcept_labels


class LabelSearchResult(DataInLabel):
    """
    A label as returned by ``GET /search/labels``.

    ``alternative_labels`` is the concept's other names -- "first nations" for
    "indigenous people". It is deliberately not on ``DataInLabel`` itself: that
    model is mirrored from the upstream data-in-api and nests inside every
    ``LabelRelationship`` on every document and passage response, where the
    field would be empty on almost every object carrying it. Only the filter
    lookup needs it, so only this endpoint returns it.

    @see: https://app.notion.com/p/4009109609a48110b89dd7bf112f97f5
    """

    alternative_labels: list[str] = Field(default=[])


# ``DataInLabel`` is declared with ``from __future__ import annotations``, so
# its ``labels: list[LabelRelationship]`` is a forward reference that resolves
# only in its own module's namespace. Subclassing it here leaves that dangling
# until the name is supplied explicitly.
LabelSearchResult.model_rebuild(
    _types_namespace={"LabelRelationship": LabelRelationship}
)
