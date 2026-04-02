from pydantic import BaseModel, Field


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
