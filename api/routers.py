import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic_settings import SettingsConfigDict

from api.labels_taxonomy import labels_taxonomy
from api.models import Aggregations, Facets, ItemResponse, SearchResponse
from api.utils import (
    DOCUMENTS_FILTERS_DESCRIPTION,
    LABELS_FILTERS_DESCRIPTION,
    PASSAGES_FILTERS_DESCRIPTION,
    documents_order_by,
    normalise_filters,
    order_by,
    pagination,
    passages_order_by,
)
from search.data_in_models import Document
from search.data_in_models import Label as DataInLabel
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


class EnvSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"), extra="allow"
    )


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]
logger.info(
    "Search settings resolved: vespa_endpoint=%s vespa_dev_instance_name=%s",
    settings.vespa_endpoint,
    settings.vespa_dev_instance_name,
)


router = APIRouter(prefix="/search")

AggregationField = Literal["aggregations.labels"]
FacetField = Literal["facets.labels.value.type", "facets.labels.type"]
Fields = AggregationField | FacetField

LLMS_TXT_PATH = Path(__file__).parent / "llms.txt"

_VESPA_UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    HTTPStatus.SERVICE_UNAVAILABLE: {
        "description": ("Vespa is unavailable, or rejected the query.")
    }
}
SEARCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.BAD_REQUEST: {"description": ("Malformed `filters` JSON")},
    **_VESPA_UNAVAILABLE_RESPONSE,
}
ITEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.NOT_FOUND: {"description": "Document not found."},
    **_VESPA_UNAVAILABLE_RESPONSE,
}


@router.get("/llms.txt", response_class=PlainTextResponse)
def read_llms_txt() -> str:
    """
    Serve the llms.txt spec that tells an agent how to query this API.

    @see: https://llmstxt.org
    """
    return LLMS_TXT_PATH.read_text(encoding="utf-8")


@router.get(
    "/documents/{document_id}",
    response_model=ItemResponse[Document],
    responses=ITEM_RESPONSES,
)
def read_document(document_id: str):
    engine = DevVespaDocumentSearchEngine(settings=settings)
    # `VespaError` deliberately propagates: `api.main.handle_vespa_error` turns
    # backend failure into a 503 for every route.
    result = engine.get(document_id)
    if result is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Document not found"
        )
    return ItemResponse(data=result)


@router.get(
    "/documents",
    response_model=SearchResponse[Document],
    responses=SEARCH_RESPONSES,
)
def read_documents(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(
        None, alias="filters", description=DOCUMENTS_FILTERS_DESCRIPTION
    ),
    # @see: https://google.aip.dev/157#read-masks-as-a-request-field
    fields: list[Fields] | None = Query(None),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(documents_order_by),
    debug: bool = False,
    bolding: bool = False,
):
    start = time.perf_counter()
    logger.info(
        "Searching documents "
        "(query=%r, page_token=%s, page_size=%s, debug=%s, bolding=%s, "
        "filters_present=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
        debug,
        bolding,
        bool(filters_json_string),
    )

    normalised_filters = normalise_filters(filters_json_string)
    requested_fields = set(fields or [])

    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding
    )
    aggregation_engines = {
        "aggregations.labels": engine.aggregations,
    }
    facet_engines = {
        "facets.labels.value.type": engine.labels_value_type_facets,
        "facets.labels.type": engine.labels_type_facets,
    }
    # Iterate the dispatch maps rather than `requested_fields` so the order is
    # deterministic and an unrecognised field cannot reach a lookup.
    requested_aggregation_fields = [
        field for field in aggregation_engines if field in requested_fields
    ]
    requested_facet_fields = [
        field for field in facet_engines if field in requested_fields
    ]
    try:
        workers = 1 + len(requested_aggregation_fields) + len(requested_facet_fields)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            f_search = pool.submit(
                engine.search,
                query=query,
                pagination=pagination,
                order_by=order_by,
                filters_json_string=normalised_filters,
            )
            f_aggregations = {
                field: pool.submit(
                    aggregation_engines[field],
                    query=query,
                    filters_json_string=normalised_filters,
                )
                for field in requested_aggregation_fields
            }
            f_facets = {
                field: pool.submit(
                    facet_engines[field],
                    query=query,
                    filters_json_string=normalised_filters,
                )
                for field in requested_facet_fields
            }
        results = f_search.result()
        aggregations_data = {
            field.removeprefix("aggregations."): future.result()
            for field, future in f_aggregations.items()
        }
        facets_data = {
            field.removeprefix("facets."): future.result()
            for field, future in f_facets.items()
        }
    except Exception:
        logger.exception(
            "Error: document search request failed "
            "(query=%r, page_token=%s, page_size=%s)",
            query,
            pagination.page_token,
            pagination.page_size,
        )
        raise

    logger.info(
        "Success: document search request completed "
        "(query=%r, results=%s, total_size=%s)",
        query,
        len(results.results),
        results.total_size,
    )

    # TODO: pagination
    took_ms = int((time.perf_counter() - start) * 1000)
    return SearchResponse[Document](
        took_ms=took_ms,
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        debug_info=engine.last_debug_info if debug else None,
        aggregations=(
            Aggregations.model_validate(aggregations_data)
            if aggregations_data
            else None
        ),
        facets=Facets.model_validate(facets_data) if facets_data else None,
    )


@router.get(
    "/labels",
    response_model=SearchResponse[DataInLabel],
    responses=SEARCH_RESPONSES,
)
def read_labels(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(
        None, alias="filters", description=LABELS_FILTERS_DESCRIPTION
    ),
    type: str | None = None,
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
):
    logger.info(
        "Searching labels "
        "(query=%r, label_type=%r, page_token=%s, page_size=%s, "
        "filters_present=%s)",
        query,
        type,
        pagination.page_token,
        pagination.page_size,
        bool(filters_json_string),
    )

    normalised_filters = normalise_filters(filters_json_string)

    engine = DevVespaLabelSearchEngine(settings=settings)
    try:
        results = engine.search(
            query=query,
            filters_json_string=normalised_filters,
            pagination=pagination,
            order_by=order_by,
            label_type=type,
        )
        engine.all_label_types()  # NOTE: Is this still being used?
    except Exception:
        logger.exception(
            "Error: label search request failed "
            "(query=%r, label_type=%r, page_token=%s, page_size=%s)",
            query,
            type,
            pagination.page_token,
            pagination.page_size,
        )
        raise

    logger.info(
        "Success: label search request completed "
        "(query=%r, label_type=%r, results=%s, total_size=%s)",
        query,
        type,
        len(results.results),
        results.total_size,
    )

    return SearchResponse[DataInLabel](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        aggregations=None,
    )


@router.get("/labels-taxonomy", response_model=SearchResponse[DataInLabel])
def read_labels_taxonomy():
    """
    Lists the labels needed for the side filter from a hardcoded list.

    @see: ./labels_taxonomy.py for the reasons why.
    """
    logger.info("Getting labels_taxonomy")

    return SearchResponse[DataInLabel](
        total_size=len(labels_taxonomy),
        page=1,
        page_size=1,
        total_pages=1,
        next_page=None,
        previous_page=None,
        results=labels_taxonomy,
        aggregations=None,
    )


@router.get(
    "/passages",
    response_model=SearchResponse[Passage],
    responses=SEARCH_RESPONSES,
)
def read_passages(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(
        None, alias="filters", description=PASSAGES_FILTERS_DESCRIPTION
    ),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(passages_order_by),
):
    logger.info(
        "Searching passages (query=%r, page_token=%s, page_size=%s, "
        "filters_present=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
        bool(filters_json_string),
    )

    normalised_filters = normalise_filters(filters_json_string)

    engine = DevVespaPassageSearchEngine(settings=settings)
    try:
        results = engine.search(
            query=query,
            pagination=pagination,
            order_by=order_by,
            filters_json_string=normalised_filters,
        )
    except Exception:
        logger.exception(
            "Error: passage search request failed "
            "(query=%r, page_token=%s, page_size=%s)",
            query,
            pagination.page_token,
            pagination.page_size,
        )
        raise

    logger.info(
        "Success: passage search request completed "
        "(query=%r, results=%s, total_size=%s)",
        query,
        len(results.results),
        results.total_size,
    )

    return SearchResponse[Passage](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        aggregations=None,
    )


@router.get("/test_labels", response_model=SearchResponse[DataInLabel])
def read_tmp_labels():
    engine = DevVespaLabelSearchEngine(settings=settings)
    results = engine.tmp_labels()
    return SearchResponse[DataInLabel](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        aggregations=None,
    )
