import base64
import json
import zlib
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, assert_never, get_args

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel

from search.engines.dev_vespa import (
    ArrayStructField,
    AttributesCondition,
    FieldFilter,
    Filter,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)


def _literal_options(model: type[BaseModel], field_name: str) -> str:
    """
    Render a model field's ``Literal`` options as a JSON alternation.

    Read off the model rather than retyped, so the published grammar tracks
    the types. Parsing ``filters`` as a model instead of a raw JSON string
    would put all of this in the generated component schema and make this
    function deletable.

    :param model: Model owning the field
    :type model: type[BaseModel]
    :param field_name: Field whose annotation is a ``Literal``
    :type field_name: str
    :return: Options joined with ``|``, each JSON-quoted
    :rtype: str
    """
    options = get_args(model.model_fields[field_name].annotation)
    return "|".join(json.dumps(option) for option in options)


FILTERS_GRAMMAR_DESCRIPTION = (
    "URL-encoded JSON filter tree, ANDed with `query`. Groups nest freely. "
    f'Group: {{"op": {_literal_options(Filter, "op")}, '
    '"filters": [<group>|<condition>]}. '
    f'Field condition: {{"field": <name>, "op": {_literal_options(FieldFilter, "op")}, '
    '"value": <string|number|boolean>}. '
    f'Attribute condition: {{"field": {_literal_options(AttributesCondition, "field")}, '
    f'"key": <string>, "op": {_literal_options(AttributesCondition, "op")}, '
    '"value": <string|number|boolean>}. '
)

ENCODING_DESCRIPTION = (
    "Encoding of `filters`. Omit to send raw JSON. "
    "Use `deflate` when `filters` is raw-deflate compressed JSON, base64url "
    'encoded (padding optional), as produced by `CompressionStream("deflate-raw")`.'
)

Encoding = Literal["deflate"] | None

_NOT_DEFLATED = "filters are not complete deflate-encoded text, or inflate past 1 MiB"


def _filters_description(
    field_map: dict[str, list[str]],
    struct_map: dict[str, ArrayStructField],
) -> str:
    """Build a `filters` description for one endpoint's filterable fields."""
    aliased = ", ".join(f"`{name}`" for name in sorted({*field_map, *struct_map}))
    return (
        f"{FILTERS_GRAMMAR_DESCRIPTION}"
        f"Recognised field names: {aliased}. Any other name is passed to the "
        "index unchanged. Semantics and worked examples: /search/llms.txt"
    )


def _normalise_datetime_value(value: str) -> int:
    """Convert an ISO-8601 datetime string to epoch seconds."""
    normalised = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalised).timestamp())


def _normalise_filter_group(filter_group: Filter) -> None:
    """Normalise supported filter values in-place."""
    for item in filter_group.filters:
        if isinstance(item, Filter):
            _normalise_filter_group(item)
            continue
        if (
            isinstance(item, AttributesCondition)
            and item.field == "attributes.published_date"
            and isinstance(item.value, str)
        ):
            try:
                item.value = _normalise_datetime_value(item.value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "published_date filters must use ISO 8601 datetimes, "
                        f"received {item.value!r}"
                    ),
                ) from exc


def _normalise_filters(filters_json_string: str) -> Filter:
    """
    Parse and normalise filter JSON before it reaches the search engine.

    ``attributes.published_date`` values are converted from ISO-8601 datetime
    strings to epoch seconds at the API boundary.
    """
    try:
        filters = Filter.model_validate_json(filters_json_string)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    _normalise_filter_group(filters)
    return filters


def _inflate_filters(encoded: str) -> str:
    try:
        # minus = raw, 15 = max stream size
        inflater = zlib.decompressobj(wbits=-15)
        padded = encoded + "=" * (-len(encoded) % 4)
        compressed = base64.urlsafe_b64decode(padded)

        # max of 1MiB decompressed to stop giant payloads
        text = inflater.decompress(compressed, 1024 * 1024).decode()
    except (ValueError, zlib.error) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _NOT_DEFLATED) from exc
    if not inflater.eof:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _NOT_DEFLATED)
    return text


def _filters_dependency(
    desc: str,
) -> Callable[[str | None, Encoding], Filter | None]:
    def _dep(
        filters: str | None = Query(None, description=desc),
        encoding: Encoding = Query(None, description=ENCODING_DESCRIPTION),
    ) -> Filter | None:
        match filters, encoding:
            case None, _:
                return None
            case str(), "deflate":
                return _normalise_filters(_inflate_filters(filters))
            case str(), None:
                return _normalise_filters(filters)
            case _:
                assert_never((filters, encoding))

    return _dep


_documents_filters = _filters_dependency(
    _filters_description(
        documents_filter_field_to_vespa_field_map,
        documents_filter_struct_field_to_vespa_field_map,
    )
)

_labels_filters = _filters_dependency(
    _filters_description(
        labels_filter_field_to_vespa_field_map,
        labels_filter_struct_field_to_vespa_field_map,
    )
)

_passages_filters = _filters_dependency(
    _filters_description(
        passages_filter_field_to_vespa_field_map,
        passages_filter_struct_field_to_vespa_field_map,
    )
)

LabelsFilterDep = Annotated[Filter | None, Depends(_labels_filters)]
DocumentsFilterDep = Annotated[Filter | None, Depends(_documents_filters)]
PassagesFilterDep = Annotated[Filter | None, Depends(_passages_filters)]
