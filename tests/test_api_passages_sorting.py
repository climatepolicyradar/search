"""Tests for passages API ``order_by`` parsing and validation."""

import pytest
from fastapi import HTTPException

from api.utils import passages_order_by


def test_passages_order_by_defaults_to_idx_asc() -> None:
    """
    Ensure ``/passages`` defaults to ascending idx order when ``order_by`` is omitted.

    :return: ``None``.
    :rtype: None
    """
    clauses = passages_order_by()
    assert len(clauses) == 1
    assert clauses[0].field == "idx"
    assert clauses[0].direction == "asc"


def test_passages_order_by_allows_supported_fields() -> None:
    """
    Ensure ``/passages`` accepts both supported sorting fields.

    :return: ``None``.
    :rtype: None
    """
    clauses = passages_order_by("relevance desc, idx asc")
    assert [clause.field for clause in clauses] == ["relevance", "idx"]


def test_passages_order_by_rejects_unsupported_field() -> None:
    """
    Ensure ``/passages`` rejects unknown fields with HTTP 400.

    :raises HTTPException: when an unsupported field is requested.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        passages_order_by("title asc")
    assert exc_info.value.status_code == 400
    assert "not supported" in str(exc_info.value.detail)


def test_passages_order_by_rejects_deprecated_page_number_field() -> None:
    """
    Ensure ``page_number`` (deprecated, being removed) is no longer accepted.

    :raises HTTPException: when ``page_number`` is requested.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        passages_order_by("page_number asc")
    assert exc_info.value.status_code == 400
    assert "not supported" in str(exc_info.value.detail)


def test_passages_order_by_rejects_invalid_direction() -> None:
    """
    Ensure invalid direction strings are rejected with HTTP 400.

    :raises HTTPException: when direction is not ``asc`` or ``desc``.
    :return: ``None``.
    :rtype: None
    """
    with pytest.raises(HTTPException) as exc_info:
        passages_order_by("idx upward")
    assert exc_info.value.status_code == 400
    assert "asc or desc" in str(exc_info.value.detail)
