from fastapi import APIRouter, Depends, Query
from pydantic_settings import SettingsConfigDict

from api.types import Aggregations, SearchResponse
from api.utils import documents_order_by, order_by, pagination
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
    engine = DevVespaDocumentSearchEngine(
        settings=settings, debug=debug, bolding=bolding
    )
    results = engine.search(
        query=query,
        pagination=pagination,
        order_by=order_by,
        filters_json_string=filters_json_string,
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
        aggregations=Aggregations(
            labels=engine.aggregations(
                query=query,
                filters_json_string=filters_json_string,
            )
        ),
    )


@router.get("/labels", response_model=SearchResponse[Label])
def read_labels(
    query: str | None = Query(None, description="What are you looking for?"),
    filters_json_string: str | None = Query(None, alias="filters"),
    type: str | None = None,
    pagination: Pagination = Depends(pagination),
    order_by: list[OrderBy] = Depends(order_by),
):
    engine = DevVespaLabelSearchEngine(settings=settings)
    results = engine.search(
        query=query,
        filters_json_string=filters_json_string,
        pagination=pagination,
        order_by=order_by,
        label_type=type,
    )
    engine.all_label_types()

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
    engine = DevVespaPassageSearchEngine(settings=settings)
    results = engine.search(
        query=query,
        pagination=pagination,
        order_by=order_by,
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
