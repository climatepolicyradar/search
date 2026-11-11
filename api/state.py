from dataclasses import dataclass
from functools import cached_property
from typing import Annotated

import httpx2
from fastapi import Depends, Request

from api.settings import settings
from api.taxonomy.service import TaxonomyService
from search.engines.dev_vespa import DevVespaLabelSearchEngine
from search.engines.dev_vespa.labels_search_engine import LabelSearchEngine


@dataclass
class State:
    httpx: httpx2.AsyncClient

    @cached_property
    def labels_engine(self) -> LabelSearchEngine:
        """The label engine backing the taxonomy."""
        return DevVespaLabelSearchEngine(settings=settings, httpx=self.httpx)

    @cached_property
    def taxonomy(self) -> TaxonomyService:
        """The polled taxonomy. Its `run()` must be entered by the lifespan."""
        return TaxonomyService(labels=self.labels_engine)


def _state(request: Request) -> State:
    return request.app.state.deps


StateDep = Annotated[
    State,
    Depends(_state),
]

def httpx(state: StateDep) -> httpx2.AsyncClient:
    """Retrieve the shared http client from app state"""
    return state.httpx

HttpxDep = Annotated[
    httpx2.AsyncClient,
    Depends(httpx),
]
