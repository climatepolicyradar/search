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
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    _DEFAULT_DOCUMENT_TOTAL_TARGET_HITS,
    _DEFAULT_PASSAGES_BREADTH_WEIGHT,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
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
    DevVespaPassageSearchEngine,
    _DEFAULT_PASSAGE_RANK_PROFILE,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)
from search.engines.vespa_query.filters import (
    ArrayStructField,
    AttributesCondition,
    ComplexExampleFilter,
    Condition,
    FieldFilter,
    Filter,
    SimpleExampleFilter,
    TOPIC_FILTER_FIELD,
    TOPIC_ID_PREFIX,
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
from search.engines.vespa_query.client import (
    API_TIMEOUT,
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,
    Settings,
    _execute_vespa_query,
    _get_total_count,
    _warn_if_degraded,
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
from search.label import Label
from search.log import get_logger

logger = get_logger(__name__)
