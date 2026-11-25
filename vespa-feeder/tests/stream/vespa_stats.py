import orjson
from vespa_feeder.stream.progress import VespaFeedStats


def vespa_stats_json(operations: int, ok: int) -> bytes:
    return orjson.dumps(
        {
            "feeder.operation.count": operations,
            "feeder.seconds": 1.5,
            "feeder.ok.count": ok,
            "feeder.error.count": 0,
            "http.response.error.count": operations - ok,
            "http.response.code.counts": {"200": ok, "500": operations - ok},
        },
        option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE,
    )


def vespa_stats(operations: int, ok: int) -> VespaFeedStats:
    return VespaFeedStats.model_validate_json(
        vespa_stats_json(operations=operations, ok=ok)
    )
