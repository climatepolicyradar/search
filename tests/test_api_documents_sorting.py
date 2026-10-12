"""Tests for documents API ``order_by`` parsing and validation."""

import pytest
from fastapi import HTTPException

from api.utils import documents_order_by, normalise_filters, parse_order_by_clauses


def test_parse_order_by_defaults_to_desc_direction() -> None:
    """
    Verify omitted direction defaults to descending order.

    :return: ``None``.
    :rtype: None
    """
    clauses = parse_order_by_clauses("title")
    assert len(clauses) == 1
    assert clauses[0].field == "title"
    assert clauses[0].direction == "desc"


def test_parse_order_by_supports_multiple_clauses() -> None:
    """
    Verify comma-separated clauses are parsed in sequence.

    :return: ``None``.
    :rtype: None
    """
    clauses = parse_order_by_clauses(
        "title asc, attributes.published_date desc",
    )
    assert len(clauses) == 2
    assert clauses[0].field == "title"
    assert clauses[0].direction == "asc"
    assert clauses[1].field == "attributes.published_date"
    assert clauses[1].direction == "desc"


def test_documents_order_by_allows_supported_fields() -> None:
    """
    Ensure ``/documents`` accepts all supported sorting fields.

    :return: ``None``.
    :rtype: None
    """
    clauses = documents_order_by("relevance desc, title asc")
    assert [clause.field for clause in clauses] == ["relevance", "title"]


def test_documents_order_by_rejects_unsupported_field() -> None:
    """
    Ensure ``/documents`` rejects unknown fields with HTTP 400.

    :raises HTTPException: when an unsupported field is requested.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        documents_order_by("title_sort asc")
    assert exc_info.value.status_code == 400
    assert "not supported" in str(exc_info.value.detail)


def test_documents_order_by_rejects_invalid_direction() -> None:
    """
    Ensure invalid direction strings are rejected with HTTP 400.

    :raises HTTPException: when direction is not ``asc`` or ``desc``.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        documents_order_by("title upward")
    assert exc_info.value.status_code == 400
    assert "asc or desc" in str(exc_info.value.detail)


def test_normalise_filters_converts_published_date_iso_to_epoch() -> None:
    """
    Ensure ``published_date`` datetime values are normalised at API boundary.

    :return: ``None``.
    :rtype: None
    """
    normalised = normalise_filters(
        """
        {
          "op": "and",
          "filters": [
            {
              "field": "attributes.published_date",
              "key": "published_date",
              "op": "gte",
              "value": "2020-01-01T00:00:00Z"
            }
          ]
        }
        """
    )
    assert normalised is not None
    assert '"value":1577836800' in normalised


def test_normalise_filters_rejects_invalid_published_date() -> None:
    """
    Ensure invalid datetime values return HTTP 400 for ``published_date``.

    :raises HTTPException: when datetime parsing fails.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        normalise_filters(
            """
            {
              "op": "and",
              "filters": [
                {
                  "field": "attributes.published_date",
                  "key": "published_date",
                  "op": "gte",
                  "value": "definitely-not-a-datetime"
                }
              ]
            }
            """
        )
    assert exc_info.value.status_code == 400
    assert "ISO 8601" in str(exc_info.value.detail)


def test_normalise_filters_rejects_empty_filter_group() -> None:
    """
    Ensure an empty filter group is rejected rather than silently dropped.

    An empty group is indistinguishable from "no constraint" once it reaches
    the YQL builder, so a caller that loses a scope gets the whole corpus back
    and no error. Rejecting it at the boundary makes that failure visible.

    :raises HTTPException: when a group contains no filters.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        normalise_filters(
            """
            {
              "op": "and",
              "filters": [
                {"op": "or", "filters": []},
                {
                  "op": "or",
                  "filters": [
                    {
                      "field": "labels.value.id",
                      "op": "contains",
                      "value": "concept::Q226"
                    }
                  ]
                }
              ]
            }
            """
        )

    assert exc_info.value.status_code == 400
    assert "empty" in str(exc_info.value.detail).lower()


def test_normalise_filters_rejects_empty_top_level_group() -> None:
    """
    Ensure a top-level group with no filters is rejected too.

    :raises HTTPException: when the top-level group contains no filters.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        normalise_filters('{"op": "and", "filters": []}')

    assert exc_info.value.status_code == 400


def test_normalise_filters_allows_a_fully_populated_group() -> None:
    """
    Ensure the rejection does not catch ordinary populated filters.

    :return: ``None``.
    :rtype: None
    """
    normalised = normalise_filters(
        """
        {
          "op": "and",
          "filters": [
            {
              "op": "or",
              "filters": [
                {
                  "field": "labels.value.id",
                  "op": "contains",
                  "value": "concept::Q226"
                }
              ]
            }
          ]
        }
        """
    )

    assert normalised is not None
