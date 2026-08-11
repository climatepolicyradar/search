"""
Client-facing shape of a passage - what the API returns and tests assert on.

Model definitions only. The `looks_like_*` rulesets that decide those flags
live in `vespa-feeder/passages_derived_data.py`, which is the single source of
truth: the feeder runs them when building the feed, and the values reach this
model already computed, via Vespa. Nothing here recomputes them - a copy in
this package would only ever be a second opinion that could disagree with the
index.
"""

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


class Label(BaseModel):
    """A label/concept node, independent of any relationship to a passage."""

    id: str = Field(default="")
    type: str = Field(default="")
    value: str = Field(default="")


class PassageLabelRelationship(BaseModel):
    """A label applied to a passage, with the fields describing that relationship."""

    value: Label
    classifier_id: str = Field(default="")
    end_index: float = Field(default=0.0)
    labelled_text: str = Field(default="")
    labellers: list[str] = Field(default_factory=list)
    prediction_probability: float = Field(default=0.0)
    start_index: float = Field(default=0.0)
    timestamps: list[str] = Field(default_factory=list)


class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    idx: int = Field(default=0)
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    looks_like_short_heading: bool = Field(default=False)
    looks_like_table_of_contents: bool = Field(default=False)
    looks_like_reference_list: bool = Field(default=False)
    pages: list[int] = Field(default_factory=list)
    pages_with_bounding_boxes: list[PageWithBoundingBoxes] = Field(default_factory=list)
    labels: list[PassageLabelRelationship] = Field(default_factory=list)
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
            looks_like_short_heading=data["looks_like_short_heading"],
            looks_like_table_of_contents=data["looks_like_table_of_contents"],
            looks_like_reference_list=data["looks_like_reference_list"],
            pages=[page["number"] for page in data["pages"]],
            pages_with_bounding_boxes=data["pages"],
            labels=[
                PassageLabelRelationship(
                    value=Label(
                        id=label["id"], type=label["type"], value=label["value"]
                    ),
                    classifier_id=label["classifier_id"],
                    end_index=label["end_index"],
                    labelled_text=label["labelled_text"],
                    labellers=label["labellers"],
                    prediction_probability=label["prediction_probability"],
                    start_index=label["start_index"],
                    timestamps=label["timestamps"],
                )
                for label in data["labels"]
            ],
            heading_id=data["heading_id"],
            heading_text=data["heading_text"],
            document_id=data["document_id"],
            principal_id=data["principal_id"],
            tokens=vespa_passage.tokens,
        )
