"""Tests for the `is_page_header_or_footer` passage flag."""

import pytest

from search.passage import Passage, is_page_header_or_footer

PAGE_HEADERS_AND_FOOTERS = {
    "page_header": "pageHeader",
    "page_footer": "pageFooter",
}

NOT_PAGE_HEADERS_OR_FOOTERS = {
    "body_text": "Text",
    "section_heading": "sectionHeading",
    "list": "List",
    "table": "Table",
    "title": "title",
    "footnote": "footnote",
    "empty": "",
}


@pytest.mark.parametrize(
    "content_type",
    PAGE_HEADERS_AND_FOOTERS.values(),
    ids=PAGE_HEADERS_AND_FOOTERS.keys(),
)
def test_whether_page_headers_and_footers_are_detected(content_type):
    assert is_page_header_or_footer(Passage(text="some text", type=content_type))


@pytest.mark.parametrize(
    "content_type",
    NOT_PAGE_HEADERS_OR_FOOTERS.values(),
    ids=NOT_PAGE_HEADERS_OR_FOOTERS.keys(),
)
def test_whether_non_page_headers_and_footers_are_not_detected(content_type):
    assert not is_page_header_or_footer(Passage(text="some text", type=content_type))
