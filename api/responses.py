"""Shared OpenAPI `responses` documentation for the routers."""

from http import HTTPStatus
from typing import Any

_VESPA_UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    HTTPStatus.TOO_MANY_REQUESTS: {"description": "Vespa throttled the query."},
    HTTPStatus.INTERNAL_SERVER_ERROR: {
        "description": "Vespa refused the query we built."
    },
    HTTPStatus.SERVICE_UNAVAILABLE: {
        "description": (
            "Vespa was unreachable, answered 5xx, or returned a body we could "
            "not parse."
        )
    },
}
SEARCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.BAD_REQUEST: {
        "description": (
            "Malformed `filters` JSON, or a URL column was asked for without "
            "`base_url`."
        )
    },
    **_VESPA_UNAVAILABLE_RESPONSE,
}
ITEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.NOT_FOUND: {"description": "Document not found."},
    **_VESPA_UNAVAILABLE_RESPONSE,
}
TAXONOMY_RESPONSES: dict[int | str, dict[str, Any]] = {
    **SEARCH_RESPONSES,
    HTTPStatus.SERVICE_UNAVAILABLE: {
        "description": (
            "Vespa was unreachable, answered 5xx, returned a body we could not "
            "parse, or the taxonomy has not been fetched from it yet."
        )
    },
}
