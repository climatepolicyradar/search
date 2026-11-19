import time
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import HttpUrl

from api.download import Column, fetch_csv
from api.filters import DocumentsFilterDep, LabelsFilterDep, PassagesFilterDep
from api.geographies_taxonomy import geographies_taxonomy
from api.health import router as health_router
from api.labels_taxonomy import labels_taxonomy
from api.models import ItemResponse, SearchResponse
from api.responses import ITEM_RESPONSES, SEARCH_RESPONSES
from api.settings import settings
from api.sitemap.routes import router as sitemap_router
from api.state import HttpxDep
from api.taxonomy.route import router as taxonomy_router
from api.utils import (
    DocumentsEngineDep,
    LabelsEngineDep,
    MsmQuery,
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
    DevVespaDocumentSearchEngine,
)
from search.label import LabelSearchResult
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


router = APIRouter(prefix="/search")
router.include_router(health_router)
router.include_router(taxonomy_router)
router.include_router(sitemap_router)

LLMS_TXT_PATH = Path(__file__).parent / "llms.txt"


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
    engine: DocumentsEngineDep,
    query: str | None = Query(None, description="What are you looking for?"),
    order_by: list[OrderBy] = Depends(documents_order_by),
    max_results: int = Query(
        500,
        gt=0,
        le=500,
        description=(
            "Maximum number of documents to include, most-relevant first. "
            "Defaults to 500, which is also the maximum."
        ),
    ),
    columns: list[Column] | None = Query(
        None,
        description=(
            "The columns to include, in the order given. Repeat the parameter "
            "per column. Omitted gives the default column set."
        ),
    ),
    base_url: HttpUrl | None = Query(
        None,
        description=(
            "Origin of the app the download is for, e.g. "
            "https://app.climatepolicyradar.org. Required when URL or "
            "BUNDLE_URL is among the columns."
        ),
    ),
):
    """
    Download the current search's results as a CSV, one row per document.

    Path is `/documents:download` (an AIP-136 custom method on the
    `documents` resource, @see: https://google.aip.dev/136) rather than
    `/documents/download`, so it can never collide with `/documents/{document_id}`.
    """

    return StreamingResponse(
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=search-results.csv"},
        content=await fetch_csv(
            engine=engine,
            columns=columns,
            query=query,
            order_by=order_by,
            filters=filters,
            max_results=max_results,
            base_url=base_url,
        ),
    )


@router.get(
    "/documents/{document_id}",
    response_model=ItemResponse[Document],
    responses=ITEM_RESPONSES,
)
async def read_document(document_id: str, httpx: HttpxDep):
    engine = DevVespaDocumentSearchEngine(settings=settings, httpx=httpx)
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
    httpx: HttpxDep,
    query: str | None = Query(None, description="What are you looking for?"),
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

    engine = DevVespaDocumentSearchEngine(
        settings=settings, httpx=httpx, debug=debug, bolding=bolding, msm=msm
    )
    try:
        results = await engine.asearch(
            query=query, pagination=pagination, order_by=order_by, filters=filters
        )
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
    )


@router.get(
    "/labels",
    response_model=SearchResponse[LabelSearchResult],
    responses=SEARCH_RESPONSES,
)
async def read_labels(
    filters: LabelsFilterDep,
    engine: LabelsEngineDep,
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
    )


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
    )
