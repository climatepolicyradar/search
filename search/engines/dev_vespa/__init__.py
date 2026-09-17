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

This module has been split into search.engines.vespa_query.* (shared
utilities) and search.engines.dev_vespa.* (engine-specific code). Everything
below is re-exported here so existing imports keep working unchanged.
"""

from __future__ import annotations

from search.engines.dev_vespa.documents_search_engine import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.labels import CountAggregation
from search.engines.dev_vespa.labels_search_engine import (
    DevVespaLabelSearchEngine,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.passages_search_engine import (
    DevVespaPassageSearchEngine,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)
from search.engines.vespa_query.client import (
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    _execute_vespa_query,
)
from search.engines.vespa_query.filters import (
    TOPIC_FILTER_FIELD,
    ArrayStructField,
    AttributesCondition,
    Condition,
    FieldFilter,
    Filter,
    _build_filter_query,
    _build_filter_yql,
    _facet_filter_label_type,
    _get_label_types_from_filters,
    _prune_filter,
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
    "CountAggregation",
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
    "_build_filter_query",
    "_build_filter_yql",
    "_execute_vespa_query",
    "_facet_filter_label_type",
    "_get_label_types_from_filters",
    "_prune_filter",
    "_ranking_overrides_for_document_order_by",
    "_ranking_overrides_for_passage_order_by",
    "_topic_ids_from_filters",
    "documents_filter_field_to_vespa_field_map",
    "documents_filter_struct_field_to_vespa_field_map",
    "labels_filter_field_to_vespa_field_map",
    "labels_filter_struct_field_to_vespa_field_map",
    "normalise_topic_id",
    "passages_filter_field_to_vespa_field_map",
    "passages_filter_struct_field_to_vespa_field_map",
    "sort_field_to_vespa_field_map",
]
