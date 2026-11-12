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
    include: list[str] | None = Query(
        None,
        description=(
            "Glob patterns over label paths, `/` between levels, `**` for any "
            "number of levels. Ancestors of a match come with it. Repeatable.\n\n"
            "- `**/keyword::*` — every keyword\n"
            "- `**/region::*` — regions alone\n"
            "- `**/region::*/**` — regions and everything under them\n"
            "- `**/category::Law/keyword::*` — keywords under a Law category"
        ),
    ),
    query: str | None = Query(None, description="What are you looking for?"),
    msm: MsmQuery = _DEFAULT_MSM,
) -> ItemResponse[list[TaxonomyNode]]:
    """Lists the label trees matching the given patterns, with document counts."""
    span = trace.get_current_span()
    span.set_attribute("taxonomy.include", include or [])

    if query is not None:
        span.set_attribute("taxonomy.query", query)

    if filters is not None:
        span.set_attribute("taxonomy.filters", filters.model_dump())

    return ItemResponse(
        data=await service.nodes(
            patterns=include,
            filters=filters,
            query=query,
            msm=msm,
        )
    )
