from fastapi import APIRouter, Depends, Query
from pydantic_settings import SettingsConfigDict

from api.types import Aggregations, SearchResponse
from api.utils import documents_order_by, normalise_filters, order_by, pagination
from search.data_in_models import Document
from search.engines import OrderBy, Pagination
from search.engines.dev_vespa import (
    DevVespaDocumentSearchEngine,
    DevVespaLabelSearchEngine,
    DevVespaPassageSearchEngine,
    Settings,
)
from search.label import Label
from search.log import get_logger
from search.passage import Passage

logger = get_logger(__name__)


class EnvSettings(Settings):
    model_config = SettingsConfigDict(env_file="api/.env")


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]


router = APIRouter(prefix="/search")


@router.get("/documents", response_model=SearchResponse[Document])
def read_documents(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(None, alias="filters"),
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(documents_order_by),
    debug: bool = False,
    bolding: bool = False,
):
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

    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding
    )
    try:
        results = engine.search(
            query=query,
            pagination=pagination,
            order_by=order_by,
            filters_json_string=normalised_filters,
        )
        labels_aggregations = engine.aggregations(
            query=query,
            filters_json_string=normalised_filters,
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
    return SearchResponse[Document](
        total_size=results.total_size,
        page=0,
        page_size=0,
        total_pages=0,
        next_page=None,
        previous_page=None,
        results=results.results,
        debug_info=engine.last_debug_info if debug else None,
        aggregations=Aggregations(labels=labels_aggregations),
    )


@router.get("/labels", response_model=SearchResponse[Label])
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
        engine.all_label_types()
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

    return SearchResponse[Label](
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
