import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic_settings import SettingsConfigDict

from api.types import Aggregations, Facets, ItemResponse, SearchResponse
from api.utils import documents_order_by, normalise_filters, order_by, pagination
from search.data_in_models import Document
from search.data_in_models import Label as DataInLabel
from search.engines import OrderBy, Pagination, VespaError
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
    model_config = SettingsConfigDict(env_file="api/.env")


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]


router = APIRouter(prefix="/search")


FacetField = Literal["facets.labels.value.type", "facets.labels.type"]


@router.get("/documents/{document_id}", response_model=ItemResponse[Document])
def read_document(document_id: str):
    engine = DevVespaDocumentSearchEngine(settings=settings)
    try:
        result = engine.get(document_id)
    except VespaError as exc:
        raise HTTPException(status_code=503, detail="Search service unavailable") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return ItemResponse(data=result)


@router.get("/documents", response_model=SearchResponse[Document])
def read_documents(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(None, alias="filters"),
    # @see: https://google.aip.dev/157#read-masks-as-a-request-field
    # Currently this is only facet fields, but might start to include
    # results and other fields
    fields: list[FacetField] | None = Query(None),
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
    requested_facet_fields = fields or []

    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding
    )
    try:
        with ThreadPoolExecutor(max_workers=2 + len(requested_facet_fields)) as pool:
            f_search = pool.submit(
                engine.search,
                query=query,
                pagination=pagination,
                order_by=order_by,
                filters_json_string=normalised_filters,
            )
            f_aggregations = pool.submit(
                engine.aggregations,
                query=query,
                filters_json_string=normalised_filters,
            )
            f_facets = {
                field: pool.submit(
                    {
                        "facets.labels.value.type": engine.labels_value_type_facets,
                        "facets.labels.type": engine.labels_type_facets,
                    }[field],
                    query=query,
                    filters_json_string=normalised_filters,
                )
                for field in requested_facet_fields
            }
        results = f_search.result()
        labels_aggregations = f_aggregations.result()
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
        aggregations=Aggregations(labels=labels_aggregations),
        facets=Facets.model_validate(facets_data) if facets_data else None,
    )


@router.get("/labels", response_model=SearchResponse[DataInLabel])
def read_labels(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(None, alias="filters"),
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


@router.get("/passages", response_model=SearchResponse[Passage])
def read_passages(
    query: str | None = Query(None, description="What are you looking for?"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
):
    logger.info(
        "Searching passages (query=%r, page_token=%s, page_size=%s)",
        query,
        pagination.page_token,
        pagination.page_size,
    )

    engine = DevVespaPassageSearchEngine(settings=settings)
    try:
        results = engine.search(
            query=query,
            pagination=pagination,
            order_by=order_by,
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
