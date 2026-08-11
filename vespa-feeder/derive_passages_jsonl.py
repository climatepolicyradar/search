"""
Apply the passages feed's derivations to JSONL, outside Prefect.

The data-lake export's records are not directly feedable: they carry `topics`
(not a `passages.sd` field, so Vespa rejects the update), no `document_ref`
(so the doc-level fields imported through it never resolve), and no
`looks_like_*` flags (so the penalties they drive in the `nativerank` profile
are inert). In production `vespa_feeder` runs `derive_passage_data` over
every record before handing the file to `vespa feed`; this script is that
same step for anyone feeding the export by hand - `vespa/justfile`'s
`feed-passages` uses it, so a local cluster holds what production holds.

Reads JSONL on stdin, writes derived JSONL on stdout:

    uv run --project vespa-feeder python vespa-feeder/derive_passages_jsonl.py \
        < raw.jsonl > derived.jsonl

Streams a line at a time rather than reading the file in, matching
`flow.py`'s `derive_data` - export chunks are ~16MB but nothing here needs
to hold one.
"""

import sys

import orjson
from passages_flow import derive_passage_data


def main() -> None:
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        record = derive_passage_data(orjson.loads(line))
        sys.stdout.buffer.write(orjson.dumps(record) + b"\n")


if __name__ == "__main__":
    main()
