from typing import Literal, Protocol

from search.data_in_models import Document, DocumentWithoutRelationships
import json

# A column is normally rendered from a `Document`, but `collections_field`
# reaches through a relationship and gets a `DocumentWithoutRelationships`. The
# two are siblings rather than parent and child, so a func usable in both
# positions has to name them both. Everything either one carries in common -
# id, title, description, attributes, labels - is readable off the union.
type AnyDocument = Document | DocumentWithoutRelationships


class FieldFunc(Protocol):
    """Pulls one CSV cell out of a document, top-level or related."""

    def __call__(self, document: AnyDocument) -> str:
        """Render this column's cell for ``document``."""
        ...


# Constrained so a typo'd column name is a type error at the template, rather
# than an ``AttributeError`` raised once per row at render time.
type DocumentField = Literal["id", "title", "description"]


def field(name: DocumentField) -> FieldFunc:
    """Read a plain top-level field straight off the document."""

    def extract(document: AnyDocument) -> str:
        value: str | None = getattr(document, name)
        return value if value is not None else ""

    return extract


def labels_field(label_type: str) -> FieldFunc:
    """Join the values of every label of ``label_type`` on the document."""

    def extract(document: AnyDocument) -> str:
        return "; ".join(
            label.value.value
            for label in document.labels
            if label.value.type == label_type
        )

    return extract


def labels_relationship_field(relationship_type: str) -> FieldFunc:
    """
    Join the values of every label attached via ``relationship_type``.

    The sibling of ``labels_field``, matching the other axis: a label carries
    its own ``type`` (what it is - an ``agent``) and is attached by a
    relationship with a ``type`` of its own (the role it plays here - a
    ``provider``). Vespa keeps these apart too, as ``labels.value`` and
    ``labels.relationship``.
    """

    def extract(document: AnyDocument) -> str:
        return "; ".join(
            label.value.value
            for label in document.labels
            if label.type == relationship_type
        )

    return extract


def activity_status_field(document: AnyDocument) -> str:
    """
    The document's activity-status timeline, as a JSON array.

    Each entry is a ``{"timestamp": ..., "value": ...}`` object. Sorted
    chronologically rather than left in the order Vespa returned the
    labels, which is arbitrary. Events with no timestamp sort last and carry a
    null ``timestamp`` - they are real events whose date we do not hold, so
    dropping them would understate the timeline.
    """
    events = [
        label for label in document.labels if label.value.type == "activity_status"
    ]
    events.sort(key=lambda label: (label.timestamp is None, label.timestamp))
    return json.dumps(
        [
            {
                "timestamp": label.timestamp.isoformat() if label.timestamp else None,
                "value": label.value.value,
            }
            for label in events
        ]
    )


def first_label_relationship_field(relationship_type: str) -> FieldFunc:
    """The first label attached via ``relationship_type``, empty if there is none."""

    def extract(document: AnyDocument) -> str:
        return next(
            (
                label.value.value
                for label in document.labels
                if label.type == relationship_type
            ),
            "",
        )

    return extract


def attributes_field(key: str) -> FieldFunc:
    """Read ``key`` out of the document's freeform attributes."""

    def extract(document: AnyDocument) -> str:
        value = document.attributes.get(key)
        return str(value) if value is not None else ""

    return extract


def url_field(base_url: str) -> FieldFunc:
    """
    Build a document's public URL from its ``deprecated_slug`` attribute.

    The slug, not the id, is what the public sites route on. A document
    without one renders empty rather than a URL built from the id, which
    would be a plausible-looking link to a page that does not exist.
    """

    def extract(document: AnyDocument) -> str:
        slug = document.attributes.get("deprecated_slug")
        return f"{base_url}/{slug}" if slug is not None else ""

    return extract


def project_id_field(read: FieldFunc) -> FieldFunc:
    """
    The number out of a ``{source}.family.{number}.{version}`` identifier.

    ``GEF.family.184.0`` renders as ``184``. An absent identifier renders
    empty; one that is present but not in that shape raises, rather than
    quietly emitting the wrong segment as a project id.
    """

    def extract(document: AnyDocument) -> str:
        identifier = read(document)
        return identifier.split(".")[2] if identifier else ""

    return extract


def collections_field(read: FieldFunc) -> FieldFunc:
    """
    Apply ``read`` to the Collection this document belongs to.

    Matches on the target's own ``entity_type::Collection`` label rather than
    on the relationship type - that label is what distinguishes a Collection
    from any other document hanging off this one. A document in no Collection
    renders empty, as does a related document, which carries no relationships
    of its own to follow.
    """

    def extract(document: AnyDocument) -> str:
        relationships = document.documents if isinstance(document, Document) else []
        collection = next(
            (
                relationship.value
                for relationship in relationships
                if any(
                    label.value.id == "entity_type::Collection"
                    for label in relationship.value.labels
                )
            ),
            None,
        )
        return read(collection) if collection is not None else ""

    return extract


ccc_csv_template: dict[str, FieldFunc] = {
    "id": field("id"),
    "title": field("title"),
    "description": field("description"),
    "url": url_field("https://www.climatecasechart.com/document"),
    "bundle_id": collections_field(field("id")),
    "bundle_title": collections_field(field("title")),
    "bundle_url": collections_field(
        url_field("https://www.climatecasechart.com/document")
    ),
    "countries": labels_field("countries"),
    "regions": labels_field("regions"),
    "subdivisions": labels_field("subdivisions"),
    "published_date": attributes_field("published_date"),
    "category": labels_field("category"),
    "provider": first_label_relationship_field("provider"),
    "status": attributes_field("status"),
    "case_status": collections_field(attributes_field("status")),
    "case_number": collections_field(attributes_field("identifier::case_number")),
    "at_issue": attributes_field("core_object"),
    "original_case_name": attributes_field("original_case_name"),
    "principal_laws": labels_field("principal_law"),
    "case_categories": labels_field("case_category"),
    "jurisdictions": labels_field("jurisdiction"),
    "activity_status_events": activity_status_field,
    "last_modified": attributes_field("last_updated_date"),
}

mcf_csv_template: dict[str, FieldFunc] = {
    "id": field("id"),
    "title": field("title"),
    "description": field("description"),
    "url": url_field("https://www.climateprojectexplorer.org/projects"),
    "countries": labels_field("countries"),
    "regions": labels_field("regions"),
    "published_date": attributes_field("published_date"),
    "entity_type": labels_field("entity_type"),
    "provider": first_label_relationship_field("provider"),
    "project_id": project_id_field(attributes_field("project_id")),
    "project_co_financing_usd": attributes_field("project_co_financing_usd"),
    "project_fund_spend_usd": attributes_field("project_fund_spend_usd"),
    "project_url": attributes_field("project_url"),
    "project_status": labels_field("project_status"),
    "focal_areas": labels_field("focal_area"),
    "implementing_agencies": labels_field("implementing_agency"),
    # The funds are `type="agent"` labels (api/labels_taxonomy.py) attached as
    # providers, so this matches the relationship rather than the label type.
    "multilateral_climate_funds": labels_relationship_field("provider"),
    "sectors": labels_field("sector"),
    "result_types": labels_field("result_type"),
    "result_areas": labels_field("result_area"),
    "themes": labels_field("theme"),
    "activity_status_events": activity_status_field,
    "last_modified": attributes_field("last_updated_date"),
}

cclw_csv_template: dict[str, FieldFunc] = {
    "id": field("id"),
    "title": field("title"),
    "description": field("description"),
    "url": url_field("https://climate-laws.org/document"),
    "countries": labels_field("countries"),
    "regions": labels_field("regions"),
    "published_date": attributes_field("published_date"),
    "document_type": labels_field("document_type"),
    "category": labels_field("category"),
    "provider": first_label_relationship_field("provider"),
    "response_areas": labels_field("response_area"),
    "keywords": labels_field("keyword"),
    "sectors": labels_field("sector"),
    "frameworks": labels_field("framework"),
    "activity_status_events": activity_status_field,
    "last_modified": attributes_field("last_updated_date"),
}


# The `?template=` API surface. A `Literal` so FastAPI rejects an unknown name
# itself, and the registry is keyed by it so adding a template without naming
# it here - or naming one that does not exist - is a type error rather than a
# `KeyError` at request time.
TemplateName = Literal["ccc", "cclw", "mcf"]

CSV_TEMPLATES: dict[TemplateName, dict[str, FieldFunc]] = {
    "ccc": ccc_csv_template,
    "cclw": cclw_csv_template,
    "mcf": mcf_csv_template,
}
