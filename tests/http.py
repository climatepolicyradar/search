import json
from typing import Any

import httpx2


class MockHandler:

    def __init__(self) -> None:
        self._requests: list[httpx2.Request] = []
        self._responses: list[dict[str, Any]] = []

    def add_response(self, json: dict[str, Any]) -> None:
        self._responses.append(json)

    def last_json(self) -> dict[str, Any]:
        return json.loads(self._requests[-1].read())

    def all_json(self) -> list[dict[str, Any]]:
        return [json.loads(request.read()) for request in self._requests]

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self._requests.append(request)
        if not self._responses:
            raise NotImplementedError()
        return httpx2.Response(200, json=self._responses.pop(0))


