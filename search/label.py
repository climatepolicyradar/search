from pydantic import BaseModel, computed_field

from search.identifier import Identifier


class Label(BaseModel):
    """Base class for a label"""

    preferred_label: str
    alternative_labels: list[str]
    negative_labels: list[str]
    description: str

    @computed_field
    @property
    def id(self) -> Identifier:
        """Return a unique ID for the concept"""
        return Identifier.generate(
            self.preferred_label,
            self.description,
            *sorted(self.alternative_labels),  # Sort for deterministic ordering
            *sorted(self.negative_labels),  # Sort for deterministic ordering
        )
