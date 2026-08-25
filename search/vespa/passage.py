"""
Canonical typed representation of the Vespa `passages` schema.

`VespaPassage` is used on both sides of the wire: building the outbound feed
update (`.to_vespa_update()`) and parsing an inbound search-hit's `fields`
dict (`VespaPassage.model_validate(fields)`). Living here rather than inside
`passages_feed_materializer.py` keeps the query path from pulling in that
module's S3/boto3/chunking dependencies; living here rather than inside
`search/passage.py` keeps "Vespa wire shape" distinct from "client API shape".
"""

from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, computed_field

from search.vespa.models import VespaAssign, VespaUpdate


class VespaCoordinate(BaseModel):
    x: float = 0.0
    y: float = 0.0


class VespaBoundingBox(BaseModel):
    coordinates: list[VespaCoordinate] = Field(default_factory=list)


class VespaPageBoxes(BaseModel):
    number: int = 0
    bounding_boxes: list[VespaBoundingBox] = Field(default_factory=list)


class VespaConcept(BaseModel):
    """
    Superseded by `VespaLabel`/`labels`.

    The `passages.sd` schema no longer has a `concepts` field. Kept only so
    `passages_feed_materializer.py`'s legacy (already schema-incompatible) path
    stays importable.
    """

    id: str = ""
    type: str = ""
    value: str = ""
    count: int = 0


class VespaLabel(BaseModel):
    # These are the core Label fields i.e. the node.
    id: str = ""
    type: str = ""
    value: str = ""
    # These are fields that relate the label to the passage i.e. the edge.
    classifier_id: str = ""
    end_index: float = 0.0
    labelled_text: str = ""
    labellers: list[str] = Field(default_factory=list)
    prediction_probability: float = 0.0
    start_index: float = 0.0
    timestamps: list[str] = Field(default_factory=list)


class VespaPassageUpdate(TypedDict):
    """The literal outbound feed JSON shape - see `VespaPassage.to_vespa_update`."""

    id: VespaAssign[str]
    idx: VespaAssign[int]
    language: VespaAssign[str]
    content: VespaAssign[str]
    looks_like_short_heading: VespaAssign[bool]
    looks_like_table_of_contents: VespaAssign[bool]
    looks_like_reference_list: VespaAssign[bool]
    looks_like_demoted_section: VespaAssign[bool]
    document_id: VespaAssign[str]
    document_ref: VespaAssign[str]
    principal_document_ref: NotRequired[VespaAssign[str]]
    content_type: NotRequired[VespaAssign[str]]
    type_confidence: NotRequired[VespaAssign[float]]
    heading_id: NotRequired[VespaAssign[str]]
    heading_text: NotRequired[VespaAssign[str]]
    labels: NotRequired[VespaAssign[list[dict[str, Any]]]]
    concept_counts: NotRequired[VespaAssign[dict[str, float]]]
    pages: NotRequired[VespaAssign[list[dict[str, Any]]]]


def flatten_vespa_tokens(token_field: Any) -> list[str]:
    """
    Flatten Vespa token summary output into a list of strings.

    Lucene linguistics with ``stemming: multiple`` returns each token as
    either a plain string or a list of stems (e.g. ``["run", "running"]``).
    This helper normalises both shapes into a flat list.
    """
    if isinstance(token_field, dict):
        items = token_field.get("values", [])
    elif isinstance(token_field, list):
        items = token_field
    else:
        return []
    flat: list[str] = []
    for item in items:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


class VespaPassage(BaseModel):
    """Canonical in-memory shape of a `passages` schema document."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    idx: int = 0
    language: str = ""
    content: str = ""
    looks_like_short_heading: bool = False
    looks_like_table_of_contents: bool = False
    looks_like_reference_list: bool = False
    looks_like_demoted_section: bool = False
    document_id: str = ""
    document_ref: str | None = None
    principal_document_ref: str | None = None
    content_type: str = ""
    type_confidence: float = 0.0
    pages: list[VespaPageBoxes] = Field(default_factory=list)
    heading_id: str | None = None
    heading_text: str | None = None
    labels: list[VespaLabel] = Field(default_factory=list)
    concept_counts: dict[str, float] = Field(default_factory=dict)

    # Imported field (from document_ref) - inbound-only, never set on feed.
    principal_id: str | None = None
    # Raw debug-summary shape for `text_tokens`; use `.tokens` for the flattened form.
    text_tokens: Any = None

    @computed_field
    @property
    def tokens(self) -> list[str]:
        """Runs flatten_vespa_tokens"""
        return flatten_vespa_tokens(self.text_tokens)

    def to_vespa_update(self) -> VespaUpdate[VespaPassageUpdate]:
        """Build the outbound partial-update feed record for this passage."""
        if not self.document_ref:
            raise ValueError("document_ref must be set to build a Vespa update")

        fields: VespaPassageUpdate = {
            "id": {"assign": self.id},
            "idx": {"assign": self.idx},
            "language": {"assign": self.language},
            "content": {"assign": self.content},
            "looks_like_short_heading": {"assign": self.looks_like_short_heading},
            "looks_like_table_of_contents": {
                "assign": self.looks_like_table_of_contents
            },
            "looks_like_reference_list": {"assign": self.looks_like_reference_list},
            "looks_like_demoted_section": {"assign": self.looks_like_demoted_section},
            "document_id": {"assign": self.document_id},
            "document_ref": {"assign": self.document_ref},
        }
        if self.principal_document_ref is not None:
            fields["principal_document_ref"] = {"assign": self.principal_document_ref}
        if self.content_type:
            fields["content_type"] = {"assign": self.content_type}
        if self.type_confidence:
            fields["type_confidence"] = {"assign": self.type_confidence}
        if self.heading_id is not None:
            fields["heading_id"] = {"assign": self.heading_id}
        if self.heading_text is not None:
            fields["heading_text"] = {"assign": self.heading_text}
        if self.labels:
            fields["labels"] = {
                "assign": [label.model_dump() for label in self.labels]
            }
        if self.concept_counts:
            fields["concept_counts"] = {"assign": self.concept_counts}
        if self.pages:
            fields["pages"] = {"assign": [page.model_dump() for page in self.pages]}

        return {
            "update": f"id:passages:passages::{self.id}",
            "create": True,
            "fields": fields,
        }
