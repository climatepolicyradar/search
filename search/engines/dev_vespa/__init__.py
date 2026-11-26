"""
Dev vespa API

Should be using the Vespa Client, but we are having problems
connecting to the remote server because of the way API Gateway
handles trailing slashes.

i.e.
VespaClient connects to `/search/`.
This isn't a viable URL for API Gatewayway, you can use
- `/search`
- `/search/{proxy+}`

The secondary URL uses a `+` which matches 1 or more characters. 🤷

For now we just use `requests` which yields the same results.
"""

from __future__ import annotations

from search.engines.dev_vespa.documents_search_engine import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    _DEFAULT_MSM,
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
)
from search.engines.dev_vespa.labels_search_engine import (
    DevVespaLabelSearchEngine,
)
from search.engines.dev_vespa.passages_search_engine import (
    DevVespaPassageSearchEngine,
)
from search.engines.vespa_query.client import (
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    aexecute_vespa_query,
)
from search.engines.vespa_query.filters import (
    TOPIC_FILTER_FIELD,
    ArrayStructField,
    AttributesCondition,
    Condition,
    FieldFilter,
    Filter,
    _build_filter_yql,
    _topic_ids_from_filters,
    normalise_topic_id,
)
from search.engines.vespa_query.sorting import (
    DOCUMENT_SORT_API_FIELDS,
    PASSAGE_SORT_API_FIELDS,
    _ranking_overrides_for_document_order_by,
    _ranking_overrides_for_passage_order_by,
    sort_field_to_vespa_field_map,
)

__all__ = [
    "ArrayStructField",
    "AttributesCondition",
    "DOCUMENT_SORT_API_FIELDS",
    "DevVespaDocumentSearchEngine",
    "DevVespaLabelSearchEngine",
    "DevVespaPassageSearchEngine",
    "DevVespaPrincipalDocumentSearchEngine",
    "Condition",
    "FieldFilter",
    "Filter",
    "HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS",
    "PASSAGE_SORT_API_FIELDS",
    "Settings",
    "TOPIC_FILTER_FIELD",
    "_DEFAULT_DOCUMENT_RANK_PROFILE",
    "_DEFAULT_MSM",
    "_build_filter_yql",
    "_ranking_overrides_for_document_order_by",
    "_ranking_overrides_for_passage_order_by",
    "_topic_ids_from_filters",
    "aexecute_vespa_query",
    "normalise_topic_id",
    "sort_field_to_vespa_field_map",
]
