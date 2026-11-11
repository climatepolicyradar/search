"""
Turn the tools' flat filter args into the `Filter` tree the engines take.

The REST API exposes the tree itself, which is flexible but easy for a model
to get wrong, so the tools take a few typed args and build it here.
"""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Annotated, Literal

from pydantic import AfterValidator, WithJsonSchema

from api.geographies_taxonomy import geographies_taxonomy
from api.labels_taxonomy import labels_taxonomy
from search.data_in_models import Label
from search.engines.dev_vespa import AttributesCondition, FieldFilter, Filter
from search.engines.vespa_query.filters import (
    TOPIC_FILTER_FIELD,
    TOPIC_ID_PREFIX,
    normalise_topic_id,
)


def _label_values(taxonomy: list[Label], label_type: str) -> list[str]:
    return [label.value for label in taxonomy if label.type == label_type]


def _one_of(allowed: list[str]) -> Callable[[str], str]:
    def check(value: str) -> str:
        if value not in allowed:
            raise ValueError(f"{value!r} isn't one of {allowed}")
        return value

    return check


CATEGORY_NAMES = _label_values(labels_taxonomy, "category")
# Stored as `topic` labels, but called response areas on the site.
RESPONSE_AREA_NAMES = _label_values(labels_taxonomy, "topic")
REGION_NAMES = _label_values(geographies_taxonomy, "region")

# Built from the taxonomies rather than as a `Literal`, which pyright requires
# to be written out. The schema keeps the list, so the model sees the choices.
Category = Annotated[
    str,
    AfterValidator(_one_of(CATEGORY_NAMES)),
    WithJsonSchema({"type": "string", "enum": CATEGORY_NAMES}),
]
ResponseArea = Annotated[
    str,
    AfterValidator(_one_of(RESPONSE_AREA_NAMES)),
    WithJsonSchema({"type": "string", "enum": RESPONSE_AREA_NAMES}),
]
Region = Annotated[
    str,
    AfterValidator(_one_of(REGION_NAMES)),
    WithJsonSchema({"type": "string", "enum": REGION_NAMES}),
]
REGION_IDS = {
    label.value: label.id for label in geographies_taxonomy if label.type == "region"
}

# Passages only see their document's labels as exact `{type}::{id}::{value}`
# strings, so a label stored under a second name won't match.
PASSAGE_DOCUMENT_LABELS_FIELD = "labels_type_id_value_attribute"
PRINCIPAL_LABEL_ID = "status::Principal"
PUBLISHED_DATE_FIELD = "attributes.published_date"

COUNTRY_NAMES = {
    label.id.removeprefix("country::"): label.value
    for label in geographies_taxonomy
    if label.type == "country"
}
TOPIC_ID = re.compile(rf"{re.escape(TOPIC_ID_PREFIX)}Q\d+")


class FilterArgError(ValueError):
    """
    A filter arg the model got wrong, with a message saying how to fix it.

    A bad label id matches nothing, so the model would just see no results.
    """


def build_filter(
    geographies: list[str] | None = None,
    regions: list[Region] | None = None,
    categories: list[Category] | None = None,
    response_areas: list[ResponseArea] | None = None,
    topics: list[str] | None = None,
    published_after: date | None = None,
    published_before: date | None = None,
    principals_only: bool = False,
    for_passages: bool = False,
) -> Filter | None:
    """
    AND together one group per arg that is set, ORing the values within it.

    :param principals_only: One result per law, policy or case, rather than
        one per version or filing.
    :param for_passages: Match countries, regions and categories on the
        passage's document, since passages only carry topics themselves.
    :raises FilterArgError: When a geography or topic isn't a valid id, or
        the date range is impossible
    :return: The filter tree, or `None` when no arg is set
    """
    if (
        published_after is not None
        and published_before is not None
        and published_after > published_before
    ):
        raise FilterArgError(
            f"published_after ({published_after}) is later than published_before "
            f"({published_before}). Swap them, or drop one."
        )
    groups: list[Filter | AttributesCondition | FieldFilter] = []
    if geographies:
        codes = [_country_code(code) for code in geographies]
        groups.append(
            _any(
                [
                    _document_label(
                        "country",
                        f"country::{code}",
                        COUNTRY_NAMES[code],
                        for_passages,
                    )
                    for code in codes
                ]
            )
        )
    if regions:
        groups.append(
            _any(
                [
                    _document_label("region", REGION_IDS[region], region, for_passages)
                    for region in regions
                ]
            )
        )
    if categories:
        groups.append(
            _any(
                [
                    _document_label(
                        "category", f"category::{category}", category, for_passages
                    )
                    for category in categories
                ]
            )
        )
    if response_areas:
        groups.append(_any([_label(f"topic::{area}") for area in response_areas]))
    if topics:
        groups.append(_any([_label(_topic_id(topic)) for topic in topics]))
    if principals_only:
        groups.append(_any([_label(PRINCIPAL_LABEL_ID)]))
    if published_after is not None:
        groups.append(_published("gte", datetime.combine(published_after, time.min)))
    if published_before is not None:
        groups.append(_published("lte", datetime.combine(published_before, time.max)))
    return Filter(op="and", filters=groups) if groups else None


def _country_code(code: str) -> str:
    normalised = code.strip().upper()
    if normalised not in COUNTRY_NAMES:
        raise FilterArgError(
            f"{code!r} isn't a country code we have. "
            "Use the ISO 3166-1 alpha-3 code, e.g. 'KEN' for Kenya."
        )
    return normalised


def _topic_id(topic: str) -> str:
    topic_id = normalise_topic_id(topic.strip())
    if not TOPIC_ID.fullmatch(topic_id):
        raise FilterArgError(
            f"{topic!r} isn't a topic id. "
            "Use search_topics to look up its id, e.g. 'concept::Q1343'."
        )
    return topic_id


def _any(filters: list[FieldFilter]) -> Filter:
    return Filter(op="or", filters=list(filters))


def _label(label_id: str) -> FieldFilter:
    return FieldFilter(field=TOPIC_FILTER_FIELD, op="contains", value=label_id)


def _document_label(
    label_type: str, label_id: str, value: str, for_passages: bool
) -> FieldFilter:
    if not for_passages:
        return _label(label_id)
    return FieldFilter(
        field=PASSAGE_DOCUMENT_LABELS_FIELD,
        op="contains",
        value=f"{label_type}::{label_id}::{value}",
    )


def _published(op: Literal["gte", "lte"], moment: datetime) -> AttributesCondition:
    # Stored as epoch seconds; the REST API converts ISO strings at its
    # boundary, and this is the MCP's boundary.
    return AttributesCondition(
        field=PUBLISHED_DATE_FIELD,
        key="published_date",
        op=op,
        value=int(moment.replace(tzinfo=UTC).timestamp()),
    )
