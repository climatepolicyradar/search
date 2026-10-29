import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from api.download import Column, fetch_documents_for_download, generate_csv
from api.filters import DocumentsFilterDep, LabelsFilterDep, PassagesFilterDep
from api.geographies_taxonomy import geographies_taxonomy
from api.health import router as health_router
from api.labels_taxonomy import labels_taxonomy
from api.models import Aggregations, Facets, ItemResponse, SearchResponse, TaxonomyNode
from api.settings import settings
from api.taxonomy import merge, taxonomy, tree
from api.utils import (
    documents_order_by,
    order_by,
    pagination,
    passages_order_by,
)
from search.data_in_models import Document
from search.data_in_models import Label as DataInLabel
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    _DEFAULT_MSM,
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
)
from search.label import LabelSearchResult
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


router = APIRouter(prefix="/search")
router.include_router(health_router)

AggregationField = Literal["aggregations.labels"]
FacetField = Literal["facets.labels.value.type", "facets.labels.type"]
Fields = AggregationField | FacetField

LLMS_TXT_PATH = Path(__file__).parent / "llms.txt"

_VESPA_UNAVAILABLE_RESPONSE: dict[int | str, dict[str, Any]] = {
    HTTPStatus.TOO_MANY_REQUESTS: {"description": "Vespa throttled the query."},
    HTTPStatus.INTERNAL_SERVER_ERROR: {
        "description": "Vespa refused the query we built."
    },
    HTTPStatus.SERVICE_UNAVAILABLE: {
        "description": (
            "Vespa was unreachable, answered 5xx, or returned a body we could "
            "not parse."
        )
    },
}
SEARCH_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.BAD_REQUEST: {"description": ("Malformed `filters` JSON")},
    **_VESPA_UNAVAILABLE_RESPONSE,
}
ITEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.NOT_FOUND: {"description": "Document not found."},
    **_VESPA_UNAVAILABLE_RESPONSE,
}


# Shared by `/documents` and `/documents:download`: a download is the same search,
# so the two must take the same threshold, or an export returns a wider set than
# the page it was exported from. See FUS-421.
MsmQuery = Annotated[
    float,
    Query(
        ge=0.0,
        le=1.0,
        description=(
            "Minimum Should Match: the fraction of the query's terms a document "
            "must contain, measured against its title and geographies, its "
            "description, or its best-matching passage. 0 (default) leaves "
            "every term optional; 1 requires all."
        ),
    ),
]


@router.get("/llms.txt", response_class=PlainTextResponse)
def read_llms_txt() -> str:
    """
    Serve the llms.txt spec that tells an agent how to query this API.

    @see: https://llmstxt.org
    """
    return LLMS_TXT_PATH.read_text(encoding="utf-8")


@router.get(
    "/documents:download",
    responses=SEARCH_RESPONSES,
)
def download_documents(
    filters: DocumentsFilterDep,
    query: str | None = Query(None, description="What are you looking for?"),
    order_by: list[OrderBy] = Depends(documents_order_by),
    max_results: int = Query(
        500,
        gt=0,
        description=(
            "Maximum number of documents to include, most-relevant first. "
            "Defaults to 500."
        ),
    ),
    columns: list[Column] | None = Query(
        None,
        description=(
            "The columns to include, in the order given. Repeat the parameter "
            "per column. Omitted gives the default column set."
        ),
    ),
    msm: MsmQuery = _DEFAULT_MSM,
):
    """
    Stream the current search's results as a CSV, one row per document.

    Path is `/documents:download` (an AIP-136 custom method on the
    `documents` resource, @see: https://google.aip.dev/136) rather than
    `/documents/download`, so it can never collide with `/documents/{document_id}`.
    """
    logger.info(
        "Downloading document search as CSV "
        "(query=%r, max_results=%s, filters_present=%s, msm=%s, columns=%s)",
        query,
        max_results,
        filters is not None,
        msm,
        columns,
    )

    engine = DevVespaDocumentSearchEngine(settings=settings, msm=msm)
    try:
        documents = fetch_documents_for_download(
            engine,
            query=query,
            order_by=order_by,
            filters=filters,
            max_results=max_results,
        )
    except Exception:
        logger.exception(
            "Error: document download request failed (query=%r, max_results=%s)",
            query,
            max_results,
        )
        raise

    logger.info(
        "Success: document download request completed (query=%r, results=%s)",
        query,
        len(documents),
    )

    return StreamingResponse(
        generate_csv(documents, columns=columns),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=search-results.csv"},
    )


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
    filters: DocumentsFilterDep,
    query: str | None = Query(None, description="What are you looking for?"),
    # @see: https://google.aip.dev/157#read-masks-as-a-request-field
    fields: list[Fields] | None = Query(None),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(documents_order_by),
    debug: bool = False,
    bolding: bool = False,
    msm: MsmQuery = _DEFAULT_MSM,
):
    start = time.perf_counter()
    logger.info(
        "Searching documents "
        "(query=%r, page_token=%s, page_size=%s, debug=%s, bolding=%s, "
        "filters_present=%s, msm=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
        debug,
        bolding,
        filters is not None,
        msm,
    )

    requested_fields = set(fields or [])

    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding, msm=msm
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
                filters=filters,
            )
            f_aggregations = {
                field: pool.submit(
                    aggregation_engines[field],
                    query=query,
                    filters=filters,
                )
                for field in requested_aggregation_fields
            }
            f_facets = {
                field: pool.submit(
                    facet_engines[field],
                    query=query,
                    filters=filters,
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
    response_model=SearchResponse[LabelSearchResult],
    responses=SEARCH_RESPONSES,
)
def read_labels(
    filters: LabelsFilterDep,
    query: str | None = Query(None, description="What are you looking for?"),
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
        filters is not None,
    )

    engine = DevVespaLabelSearchEngine(settings=settings)
    try:
        results = engine.search(
            query=query,
            filters=filters,
            pagination=pagination,
            order_by=order_by,
            label_type=type,
        )
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

    return SearchResponse[LabelSearchResult](
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

    
GeographyType = Literal["region", "country", "subdivision"]


@router.get("/geographies-taxonomy", response_model=SearchResponse[DataInLabel])
def read_geographies_taxonomy(
    geography_type: list[GeographyType] | None = Query(None, alias="type"),
):
    """
    Lists the region/country/subdivision hierarchy from a hardcoded list.

    @see: ./geographies_taxonomy.py for the reasons why.
    """
    logger.info("Getting geographies_taxonomy (type=%r)", geography_type)

    results = (
        [label for label in geographies_taxonomy if label.type in geography_type]
        if geography_type
        else geographies_taxonomy
    )

    return SearchResponse[DataInLabel](
        total_size=len(results),
        page=1,
        page_size=1,
        total_pages=1,
        next_page=None,
        previous_page=None,
        results=results,
        aggregations=None,
    )


@router.get(
    "/taxonomy",
    response_model=ItemResponse[list[TaxonomyNode]],
    responses=SEARCH_RESPONSES,
)
def read_taxonomy(
    filters: DocumentsFilterDep,
    label_type: list[str] | None = Query(None, alias="type"),
):
    """Lists label trees of the given types, with document counts."""
    logger.info("Getting taxonomy (type=%r)", label_type)

    label_engine = DevVespaLabelSearchEngine(settings=settings)
    document_engine = DevVespaDocumentSearchEngine(settings=settings)

    merged = merge(taxonomy, label_engine.all_labels())
    nodes = tree(merged, label_type)

    counts = document_engine.label_counts(
        label_types=sorted(set().union(*(node.types() for node in nodes))),
        filters=filters,
    )

    for node in nodes:
        node.set_count(counts)

    return ItemResponse(data=[node.response() for node in nodes])


@router.get(
    "/passages",
    response_model=SearchResponse[Passage],
    responses=SEARCH_RESPONSES,
)
def read_passages(
    filters: PassagesFilterDep,
    query: str | None = Query(None, description="What are you looking for?"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(passages_order_by),
    bolding: bool = False,
):
    logger.info(
        "Searching passages (query=%r, page_token=%s, page_size=%s, bolding=%s, "
        "filters_present=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
        bolding,
        filters is not None,
    )

    engine = DevVespaPassageSearchEngine(settings=settings)
    try:
        results = engine.search(
            query=query,
            pagination=pagination,
            order_by=order_by,
            filters=filters,
            bolding=bolding,
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


PassageMsmQuery = Annotated[
    float,
    Query(
        ge=0.0,
        le=1.0,
        description=(
            "Minimum Should Match for `query`: the fraction of its terms a passage "
            "must contain to match on the text. A passage matching `filters` is "
            "kept regardless. 0 (default) leaves every term optional; 1 requires all."
        ),
    ),
]


@router.get(
    "/passages:within",
    response_model=SearchResponse[Passage],
    responses=SEARCH_RESPONSES,
)
def read_passages_within(
    filters: PassagesFilterDep,
    document_id: list[str] = Query(
        ...,
        min_length=1,
        description=(
            "Search the passages of these documents. A Principal's id covers "
            "every one of its members."
        ),
    ),
    query: str | None = Query(None, description="What are you looking for?"),
    msm: PassageMsmQuery = 0.0,
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(passages_order_by),
    bolding: bool = False,
):
    logger.info(
        "Searching passages within documents (document_ids=%r, query=%r, "
        "msm=%s, page_token=%s, page_size=%s, bolding=%s, filters_present=%s)",
        document_id,
        query,
        msm,
        pagination.page_token,
        pagination.page_size,
        bolding,
        filters is not None,
    )

    engine = DevVespaPassageSearchEngine(settings=settings)
    try:
        results = engine.search_within(
            document_ids=document_id,
            query=query,
            pagination=pagination,
            order_by=order_by,
            filters=filters,
            msm=msm,
            bolding=bolding,
        )
    except Exception:
        logger.exception(
            "Error: passages within documents search request failed "
            "(document_ids=%r, query=%r, page_token=%s, page_size=%s)",
            document_id,
            query,
            pagination.page_token,
            pagination.page_size,
        )
        raise

    logger.info(
        "Success: passages within documents search request completed "
        "(document_ids=%r, query=%r, results=%s, total_size=%s)",
        document_id,
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
