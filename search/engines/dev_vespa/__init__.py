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

from typing import Any

from search.data_in_models import Label as DataInLabel
from search.data_in_models import LabelRelationship
from search.engines import ListResponse, OrderBy, Pagination, SearchEngine
from search.engines.dev_vespa.documents_search_engine import (  # noqa: F401
    _DEFAULT_DOCUMENT_RANK_PROFILE,
    DevVespaDocumentSearchEngine,
    DevVespaPrincipalDocumentSearchEngine,
    documents_filter_field_to_vespa_field_map,
    documents_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.labels import (
    CountAggregation,  # noqa: F401
    DevVespaInstanceAddIn,
)
from search.engines.dev_vespa.labels_search_engine import (
    DevVespaLabelSearchEngine,
    labels_filter_field_to_vespa_field_map,
    labels_filter_struct_field_to_vespa_field_map,
)
from search.engines.dev_vespa.passages_search_engine import (  # noqa: F401
    DevVespaPassageSearchEngine,
    passages_filter_field_to_vespa_field_map,
    passages_filter_struct_field_to_vespa_field_map,
)
from search.engines.vespa_query.client import (
    HTTP_ERROR_PREVIEW_LIMIT_CHARACTERS,  # noqa: F401
    Settings,
    _execute_vespa_query,
    _get_total_count,
)
from search.engines.vespa_query.filters import (  # noqa: F401
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
from search.engines.vespa_query.query_text import _strip_quotes
from search.engines.vespa_query.sorting import (  # noqa: F401
    DOCUMENT_SORT_API_FIELDS,
    PASSAGE_SORT_API_FIELDS,
    _ranking_overrides_for_document_order_by,
    _ranking_overrides_for_passage_order_by,
    sort_field_to_vespa_field_map,
)
from search.log import get_logger

logger = get_logger(__name__)
