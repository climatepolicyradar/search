"""Typed wrappers for the shape of a Vespa query response."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from search.engines.vespa_query.client import VespaError


class VespaResponseError(BaseModel):
    code: int
    summary: str
    message: str | None = None


class VespaHit[A: BaseModel](BaseModel):
    fields: A


class VespaRoot[A: BaseModel](BaseModel):
    errors: list[VespaResponseError] = []
    children: list[A] | None = None

    def raise_if_errors(self, request_context: str) -> None:
        """Raise when Vespa reported an error in the body of a 200."""
        if not self.errors:
            return

        reported = ", ".join(
            f"{error.summary} {error.message}".strip() for error in self.errors
        )

        raise VespaError(
            f"Vespa reported errors [{request_context}]: {reported}",
            status_code=None,
        )


class VespaResponse[A: BaseModel](BaseModel):
    root: VespaRoot[A]


class ByNameModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
