"""Shared policy for turning a failed dependency into an HTTP status."""

from http import HTTPStatus

from search.engines import VespaError


def vespa_error_status(exc: VespaError) -> HTTPStatus:
    """
    Pick the status that tells the truth about a failed Vespa request.

    503: Vespa was unreachable, answered 5xx, or returned a body we could not parse.
    500: Vespa refused the query we built.
    429: Vespa throttled the query.
    404: This document is missing
    """
    if exc.status_code is None:
        # retry: We don't know what the error was and will likely fix itself
        return HTTPStatus.SERVICE_UNAVAILABLE
    if exc.status_code == HTTPStatus.TOO_MANY_REQUESTS:
        # retry: if you slow down, you can retry in a bit
        return HTTPStatus.TOO_MANY_REQUESTS
    if exc.status_code == HTTPStatus.NOT_FOUND:
        # no-retry: this document is not there
        return HTTPStatus.NOT_FOUND
    if HTTPStatus.BAD_REQUEST <= exc.status_code < HTTPStatus.INTERNAL_SERVER_ERROR:
        # no-retry: this is a search application error, and retrying will not fix it and potentially make it worse
        return HTTPStatus.INTERNAL_SERVER_ERROR
    # retry: Vespa is having a bad day, and retrying later may work
    return HTTPStatus.SERVICE_UNAVAILABLE
