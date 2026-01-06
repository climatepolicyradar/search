from knowledge_graph.identifiers import Identifier
from pydantic import BaseModel, computed_field


class Label(BaseModel):
    """Base class for a label"""

    preferred_label: str
    alternative_labels: list[str]
    negative_labels: list[str]
    description: str | None = None

    @computed_field
    @property
    def id(self) -> Identifier:
        """Return a unique ID for the concept"""
        return Identifier.generate(
            self.preferred_label,
            self.description or "",
            *sorted(self.alternative_labels),  # Sort for deterministic ordering
            *sorted(self.negative_labels),  # Sort for deterministic ordering
        )

    @computed_field
    @property
    def all_labels(self) -> list[str]:
        """The preferred label, and the alternative labels"""

        return [self.preferred_label] + self.alternative_labels

    @computed_field
    @property
    def all_labels_lowercased(self) -> list[str]:
        """Lowercased preferred label, and the alternative labels"""

        return [lbl.lower() for lbl in self.all_labels]
