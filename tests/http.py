import json
from typing import Any

import httpx2


class MockHandler:

    def __init__(self) -> None:
        self._requests: list[httpx2.Request] = []
        self._outcomes: list[httpx2.Response | Exception] = []

    @property
    def request_count(self) -> int:
        return len(self._requests)

    def add_response(self, json: dict[str, Any]) -> None:
        self._outcomes.append(httpx2.Response(200, json=json))

    def add_text_response(self, status_code: int, text: str) -> None:
        self._outcomes.append(httpx2.Response(status_code, text=text))

    def add_error(self, error: Exception) -> None:
        self._outcomes.append(error)

    def last_json(self) -> dict[str, Any]:
        return json.loads(self._requests[-1].read())

    def all_json(self) -> list[dict[str, Any]]:
        return [json.loads(request.read()) for request in self._requests]

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self._requests.append(request)
        if not self._outcomes:
            raise NotImplementedError()
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
