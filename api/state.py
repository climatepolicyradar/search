from typing import Annotated, TypedDict, cast

import httpx2
from fastapi import Depends, Request


class State(TypedDict):
    httpx: httpx2.AsyncClient


def _state(request: Request) -> State:
    return cast("State", request.app.state)

StateDep = Annotated[
    State,
    Depends(_state),
]

def httpx(state: StateDep) -> httpx2.AsyncClient:
    """Retrieve the shared http client from app state"""
    return state["httpx"]

HttpxDep = Annotated[
    httpx2.AsyncClient,
    Depends(httpx),
]
