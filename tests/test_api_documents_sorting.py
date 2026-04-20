"""Tests for documents API ``order_by`` parsing and validation."""

import pytest
from fastapi import HTTPException

from api.utils import documents_order_by, parse_order_by_clauses


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
