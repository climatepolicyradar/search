import asyncio
import time
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any, Literal, get_args

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from api.download import Column, fetch_documents_for_download, generate_csv
from api.filters import DocumentsFilterDep, LabelsFilterDep, PassagesFilterDep
from api.geographies_taxonomy import geographies_taxonomy
from api.health import router as health_router
from api.labels_taxonomy import labels_taxonomy
from api.models import Aggregations, Facets, ItemResponse, SearchResponse
from api.settings import settings
from api.utils import (
    PassagesEngineDep,
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
    CountAggregation,
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
)
from search.label import Label, LabelSearchResult
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
async def download_documents(
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
        documents = await fetch_documents_for_download(
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
async def read_document(document_id: str):
    engine = DevVespaDocumentSearchEngine(settings=settings)
    # `VespaError` deliberately propagates: `api.main.handle_vespa_error` turns
    # backend failure into a 503 for every route.
    result = await engine.aget(document_id)
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
async def read_documents(
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
        "aggregations.labels": engine.aaggregations,
    }
    facet_engines = {
        "facets.labels.value.type": engine.alabels_value_type_facets,
        "facets.labels.type": engine.alabels_type_facets,
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
        results, extra_results = await asyncio.gather(
            engine.asearch(
                query=query, pagination=pagination, order_by=order_by, filters=filters
            ),
            asyncio.gather(
                *(
                    aggregation_engines[field](query=query, filters=filters)
                    for field in requested_aggregation_fields
                ),
                *(
                    facet_engines[field](query=query, filters=filters)
                    for field in requested_facet_fields
                ),
            ),
        )
        aggregation_results = extra_results[: len(requested_aggregation_fields)]
        facet_results = extra_results[len(requested_aggregation_fields) :]
        aggregations_data = {
            field.removeprefix("aggregations."): result
            for field, result in zip(requested_aggregation_fields, aggregation_results)
        }
        facets_data = {
            field.removeprefix("facets."): result
            for field, result in zip(requested_facet_fields, facet_results)
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
async def read_labels(
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
        results = await engine.asearch(
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
    "/geographies:aggregate",
    response_model=ItemResponse[list[CountAggregation[Label]]],
    responses=SEARCH_RESPONSES,
)
async def aggregate_geographies(
    filters: DocumentsFilterDep,
    geography_type: list[GeographyType] | None = Query(
        None,
        alias="labels.value.type",
        description=(
            "Restrict the aggregation to these geography label types. "
            "Omit to return every geography type."
        ),
    ),
    query: str | None = Query(None, description="What are you looking for?"),
):
    """
    Count documents per geography label, scoped by `filters`.

    Answers "which geographies have data here?" - a caller passes the same
    filters it sends to `/documents`, so the list it builds and the results
    it shows describe the same document set (@see FUS-475).

    Only geographies that match are returned: the counts come from a Vespa
    grouping query, and a group cannot exist without a document in it.

    Returns counts only. The region/country/subdivision hierarchy lives in
    `/geographies-taxonomy`; callers join the two on label id.
    """
    logger.info(
        "Aggregating geographies (query=%r, geography_type=%r, filters_present=%s)",
        query,
        geography_type,
        filters is not None,
    )

    engine = DevVespaDocumentSearchEngine(settings=settings)
    try:
        aggregations = await engine.aaggregations(query=query, filters=filters)
    except Exception:
        logger.exception(
            "Error: geography aggregation request failed (query=%r, geography_type=%r)",
            query,
            geography_type,
        )
        raise

    # `aggregations()` groups every label and concept on the matching documents,
    # not just geographies, so the fallback is a whitelist rather than a no-op.
    wanted = set(geography_type) if geography_type else set(get_args(GeographyType))
    results = [
        aggregation for aggregation in aggregations if aggregation.value.type in wanted
    ]

    logger.info(
        "Success: geography aggregation completed (query=%r, results=%s)",
        query,
        len(results),
    )

    return ItemResponse(data=results)


@router.get(
    "/passages",
    response_model=SearchResponse[Passage],
    responses=SEARCH_RESPONSES,
)
async def read_passages(
    filters: PassagesFilterDep,
    engine: PassagesEngineDep,
    query: str | None = Query(None, description="What are you looking for?"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(passages_order_by),
    bolding: bool = False,
):
    logger.info(
        "Searching passages (query=%r, page_token=%s, page_size=%s, bolding=%s, "
        "rank_profile=%s, filters_present=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
        bolding,
        engine.ranking_profile,
        filters is not None,
    )

    try:
        results = await engine.asearch(
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
async def read_passages_within(
    filters: PassagesFilterDep,
    engine: PassagesEngineDep,
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
        "msm=%s, page_token=%s, page_size=%s, bolding=%s, rank_profile=%s, "
        "filters_present=%s)",
        document_id,
        query,
        msm,
        pagination.page_token,
        pagination.page_size,
        bolding,
        engine.ranking_profile,
        filters is not None,
    )

    try:
        results = await engine.asearch_within(
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
