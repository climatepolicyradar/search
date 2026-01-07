from pydantic import BaseModel, computed_field

from search.identifiers import IdentifierWithSuffix


class Label(BaseModel):
    """Base class for a label"""

    preferred_label: str
    alternative_labels: list[str]
    negative_labels: list[str]
    description: str | None = None
    source: str
    id_at_source: str

    @computed_field
    @property
    def id(self) -> IdentifierWithSuffix:
        """Return a unique ID for the concept"""
        return IdentifierWithSuffix.generate(
            self.source,
            self.id_at_source,
            suffix=self.id_at_source,
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
