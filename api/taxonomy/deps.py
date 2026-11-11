from typing import Annotated

from fastapi import Depends

from api.state import StateDep
from api.taxonomy.service import TaxonomyService


def _taxonomy_service(state: StateDep) -> TaxonomyService:
    return state.taxonomy


TaxonomyServiceDep = Annotated[
    TaxonomyService,
    Depends(_taxonomy_service),
]
