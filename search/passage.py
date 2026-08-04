from pydantic import BaseModel, Field, computed_field

from search.vespa.passage import VespaPassage


class Coordinate(BaseModel):
    """A single x/y point in a bounding-box polygon."""

    x: float = Field(default=0.0)
    y: float = Field(default=0.0)


class BoundingBox(BaseModel):
    """A polygon (list of coordinate points) bounding part of a passage on a page."""

    coordinates: list[Coordinate] = Field(default_factory=list)


class PageWithBoundingBoxes(BaseModel):
    """A page number paired with the bounding boxes locating a passage on it."""

    number: int = Field(default=0)
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)


class Concept(BaseModel):
    """A concept/topic mentioned within a passage, with its mention count."""

    id: str = Field(default="")
    type: str = Field(default="")
    value: str = Field(default="")
    count: int = Field(default=0)


class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    idx: int = Field(default=0)
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    pages: list[int] = Field(default_factory=list)
    pages_with_bounding_boxes: list[PageWithBoundingBoxes] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    heading_id: str | None = Field(default=None)
    heading_text: str | None = Field(default=None)
    document_id: str = Field(default="")
    principal_id: str | None = Field(default=None)
    # TODO: this is Vespa's own on-the-fly tokenization of `text` (via
    # debug-summary), NOT the same as the Snowflake model's `tokens` column
    # (Python-side tokenization fed INTO Vespa). Will likely remove this field
    # in the future - just here for now to expose for discovery for the UI
    # project.
    tokens: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id

    @classmethod
    def from_vespa_passage(cls, vespa_passage: VespaPassage) -> "Passage":
        """Build the client-facing `Passage` from a canonical `VespaPassage`."""
        data = vespa_passage.model_dump()
        return cls(
            text_block_id=data["id"],
            idx=data["idx"],
            text=data["content"],
            language=data["language"],
            type=data["content_type"],
            type_confidence=data["type_confidence"],
            pages=[page["number"] for page in data["pages"]],
            pages_with_bounding_boxes=data["pages"],
            concepts=data["concepts"],
            heading_id=data["heading_id"],
            heading_text=data["heading_text"],
            document_id=data["document_id"],
            principal_id=data["principal_id"],
            tokens=vespa_passage.tokens,
        )
