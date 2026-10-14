"""
Long-lived dependencies, created once in the app lifespan and shared by every request.

Routes never take `AppState` itself: each thing held here gets its own dependency,
so a route declares only what it uses.
"""

from dataclasses import dataclass
from typing import Annotated

import requests
from fastapi import Depends, Request


@dataclass(frozen=True)
class AppState:
    # Generic, so it can be shared by any upstream: no service's headers or auth.
    http: requests.Session


def get_app_state(request: Request) -> AppState:
    """The state yielded by the lifespan, which Starlette copies onto each request."""
    return request.state.app_state


AppStateDep = Annotated[AppState, Depends(get_app_state)]


def http_session(state: AppStateDep) -> requests.Session:
    return state.http


HttpSessionDep = Annotated[requests.Session, Depends(http_session)]
