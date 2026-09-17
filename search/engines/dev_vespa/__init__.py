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

# The three engines.
from search.engines.dev_vespa.documents_search_engine import (
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    _DEFAULT_DOCUMENT_TOTAL_TARGET_HITS,
    _DEFAULT_PASSAGES_BREADTH_WEIGHT,
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)

# Shared engine helpers.
from search.engines.dev_vespa.labels import (
    MISSING_PLACEHOLDER,
    CountAggregation,
    DevVespaInstanceAddIn,
    get_labels_from_vespa_response,
)
from search.engines.dev_vespa.labels_search_engine import (
    DevVespaLabelSearchEngine,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.passages_search_engine import (
    _DEFAULT_PASSAGE_RANK_PROFILE,
    DevVespaPassageSearchEngine,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)

# Shared query-building utilities.
from search.engines.vespa_query.client import (
    API_TIMEOUT,
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    _execute_vespa_query,
    _get_total_count,
    _warn_if_degraded,
)
from search.engines.vespa_query.filters import (
    TOPIC_FILTER_FIELD,
    TOPIC_ID_PREFIX,
    ArrayStructField,
    AttributesCondition,
    ComplexExampleFilter,
    Condition,
    FieldFilter,
    Filter,
    SimpleExampleFilter,
    _build_condition_yql,
    _build_filter_query,
    _build_filter_yql,
    _facet_filter_label_type,
    _format_value,
    _get_label_types_from_filters,
    _prune_filter,
    _published_date_operand,
    _to_unix_timestamp,
    _topic_ids_from_filters,
    _value_type_to_vespa_attributes_field,
    normalise_topic_id,
)
from search.engines.vespa_query.query_text import (
    CURRENCY_SYMBOL_REPLACEMENTS,
    GEOGRAPHY_ALIASES,
    _fold_accents,
    _normalize_currency_symbols,
    _resolve_geography_aliases,
    _strip_quotes,
)
from search.engines.vespa_query.sorting import (
    DOCUMENT_SORT_API_FIELDS,
    PASSAGE_SORT_API_FIELDS,
    _document_sort_ranking_string,
    _passage_sort_ranking_string,
    _ranking_overrides_for_document_order_by,
    _ranking_overrides_for_passage_order_by,
    passage_sort_field_to_vespa_field_map,
    sort_field_to_vespa_field_map,
)

# Every name above is imported for re-export, not used in this file - kept out
# of ruff's unused-import check (F401) by listing them all here.
__all__ = [
    "API_TIMEOUT",
    "ArrayStructField",
    "AttributesCondition",
    "CURRENCY_SYMBOL_REPLACEMENTS",
    "ComplexExampleFilter",
    "Condition",
    "CountAggregation",
    "DOCUMENT_SORT_API_FIELDS",
    "DevVespaDocumentSearchEngine",
    "DevVespaInstanceAddIn",
    "DevVespaLabelSearchEngine",
    "DevVespaPassageSearchEngine",
    "DevVespaPrincipalDocumentSearchEngine",
    "FieldFilter",
    "Filter",
    "GEOGRAPHY_ALIASES",
    "HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS",
    "MISSING_PLACEHOLDER",
    "PASSAGE_SORT_API_FIELDS",
    "Settings",
    "SimpleExampleFilter",
    "TOPIC_FILTER_FIELD",
    "TOPIC_ID_PREFIX",
    "_DEFAULT_DOCUMENT_RANK_PROFILE",
    "_DEFAULT_DOCUMENT_TOTAL_TARGET_HITS",
    "_DEFAULT_PASSAGES_BREADTH_WEIGHT",
    "_DEFAULT_PASSAGE_RANK_PROFILE",
    "_build_condition_yql",
    "_build_filter_query",
    "_build_filter_yql",
    "_document_sort_ranking_string",
    "_execute_vespa_query",
    "_facet_filter_label_type",
    "_fold_accents",
    "_format_value",
    "_get_label_types_from_filters",
    "_get_total_count",
    "_normalize_currency_symbols",
    "_passage_sort_ranking_string",
    "_prune_filter",
    "_published_date_operand",
    "_ranking_overrides_for_document_order_by",
    "_ranking_overrides_for_passage_order_by",
    "_resolve_geography_aliases",
    "_strip_quotes",
    "_to_unix_timestamp",
    "_topic_ids_from_filters",
    "_value_type_to_vespa_attributes_field",
    "_warn_if_degraded",
    "documents_filter_field_to_vespa_field_map",
    "documents_filter_struct_field_to_vespa_field_map",
    "get_labels_from_vespa_response",
    "labels_filter_field_to_vespa_field_map",
    "labels_filter_struct_field_to_vespa_field_map",
    "normalise_topic_id",
    "passage_sort_field_to_vespa_field_map",
    "passages_filter_field_to_vespa_field_map",
    "passages_filter_struct_field_to_vespa_field_map",
    "sort_field_to_vespa_field_map",
]
