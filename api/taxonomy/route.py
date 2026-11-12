from fastapi import APIRouter, Query
from opentelemetry import trace

from api.filters import DocumentsFilterDep
from api.models import ItemResponse
from api.responses import TAXONOMY_RESPONSES
from api.taxonomy.deps import TaxonomyServiceDep
from api.taxonomy.models import TaxonomyNode
from api.utils import MsmQuery
from search.engines.dev_vespa import _DEFAULT_MSM

router = APIRouter(tags=["taxonomy"])


@router.get(
    "/labels:taxonomy",
    response_model=ItemResponse[list[TaxonomyNode]],
    responses=TAXONOMY_RESPONSES,
)
async def read_taxonomy(
    filters: DocumentsFilterDep,
    service: TaxonomyServiceDep,
    label_type: list[str] | None = Query(None, alias="type"),
    label_id: list[str] | None = Query(None, alias="id"),
    query: str | None = Query(None, description="What are you looking for?"),
    msm: MsmQuery = _DEFAULT_MSM,
) -> ItemResponse[list[TaxonomyNode]]:
    """Lists label trees of the given types or ids, with document counts."""
    span = trace.get_current_span()
    span.set_attribute("taxonomy.types", label_type or [])
    span.set_attribute("taxonomy.ids", label_id or [])

    if query is not None:
        span.set_attribute("taxonomy.query", query)

    if filters is not None:
        span.set_attribute("taxonomy.filters", filters.model_dump())

    return ItemResponse(
        data=await service.nodes(
            label_types=label_type,
            label_ids=label_id,
            filters=filters,
            query=query,
            msm=msm,
        )
    )
