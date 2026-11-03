"""Table-driven tests for the feeder's S3 discovery and download helpers."""

import pytest
import vespa_feeder as feeder
from helpers import put_s3_objects, read_jsonl, write_jsonl


def _put_export_prefixes(s3_client, bucket: str, prefix: str, names: list[str]) -> None:
    """
    Create a real object under each export name, so S3 derives the prefixes.

    `get_latest_s3_export_prefix` paginates with `Delimiter="/"`, which is what
    rolls these keys up into `CommonPrefixes` entries holding only the export
    names. Writing real objects rather than handing back canned prefixes is the
    point: the delimiter semantics are exercised rather than assumed.
    """
    for name in names:
        s3_client.put_object(Bucket=bucket, Key=f"{prefix}{name}part-0.jsonl", Body=b"")


@pytest.mark.parametrize(
    ("export_names", "expected"),
    [
        pytest.param(
            ["20260922T190625Z/", "20260923T190625Z/"],
            "20260923T190625Z",
            id="newest-of-two",
        ),
        pytest.param(
            ["20260923T190625Z/", "20260922T190625Z/"],
            "20260923T190625Z",
            id="listing-order-does-not-matter",
        ),
        pytest.param(
            ["20260924T003000Z/", "20260924T010000Z/"],
            "20260924T010000Z",
            id="same-day-later-time",
        ),
        pytest.param(
            ["20260923T190625Z/", "latest/"],
            "20260923T190625Z",
            id="ignores-latest",
        ),
    ],
)
def test_get_latest_s3_export_prefix_returns_the_newest_timestamped_prefix(
    s3_client, s3_bucket, export_names, expected
):
    _put_export_prefixes(s3_client, s3_bucket, "a/prefix/", export_names)

    assert (
        feeder.get_latest_s3_export_prefix(bucket=s3_bucket, prefix="a/prefix/")
        == expected
    )


def test_get_latest_s3_export_prefix_reads_every_page(s3_client, s3_bucket):
    """
    `CommonPrefixes` caps at 1000 per page, so the newest can land on page two.

    Listing is lexicographic, so the newest timestamp is also the last one S3
    returns - stopping at the first page would miss it entirely.
    """
    export_names = [f"202609{day:02d}T010000Z/" for day in range(1, 31)]
    export_names += [
        f"20260930T{minute // 60:02d}{minute % 60:02d}00Z/" for minute in range(1000)
    ]
    _put_export_prefixes(s3_client, s3_bucket, "a/prefix/", export_names)

    assert (
        feeder.get_latest_s3_export_prefix(bucket=s3_bucket, prefix="a/prefix/")
        == "20260930T163900Z"
    )


@pytest.mark.parametrize(
    ("export_names", "unrelated_keys"),
    [
        pytest.param([], [], id="no-pages"),
        pytest.param([], ["another/prefix/20260923T190625Z/part-0.jsonl"], id="empty-page"),
        pytest.param(["latest/"], [], id="only-latest"),
        pytest.param(["not-a-timestamp/"], [], id="unrecognised-prefix"),
        pytest.param(["20260923T190625/"], [], id="timestamp-missing-the-z"),
    ],
)
def test_get_latest_s3_export_prefix_raises_when_there_is_no_timestamped_prefix(
    s3_client, s3_bucket, export_names, unrelated_keys
):
    _put_export_prefixes(s3_client, s3_bucket, "a/prefix/", export_names)
    for key in unrelated_keys:
        s3_client.put_object(Bucket=s3_bucket, Key=key, Body=b"")

    with pytest.raises(FileNotFoundError, match="No timestamped snapshots"):
        feeder.get_latest_s3_export_prefix(bucket=s3_bucket, prefix="a/prefix/")

@pytest.mark.parametrize(
    ("keys", "prefix", "expected"),
    [
        pytest.param(
            ["export/20260929T010000Z/b.jsonl", "export/20260929T010000Z/a.jsonl"],
            "export/20260929T010000Z",
            ["export/20260929T010000Z/a.jsonl", "export/20260929T010000Z/b.jsonl"],
            id="prefix-is-a-directory-sorted",
        ),
        pytest.param(
            [
                "export/20260929T010000Z/a.jsonl",
                "export/20260929T010000Z-retry/b.jsonl",
            ],
            "export/20260929T010000Z",
            ["export/20260929T010000Z/a.jsonl"],
            id="sibling-sharing-the-string-prefix-is-excluded",
        ),
    ],
)
def test_list_s3_keys(s3_client, s3_bucket, keys, prefix, expected):
    for key in keys:
        s3_client.put_object(Bucket=s3_bucket, Key=key, Body=b"")

    assert feeder.list_s3_keys(bucket=s3_bucket, prefix=prefix) == expected


def test_list_s3_keys_raises_when_the_prefix_is_empty(s3_client, s3_bucket):
    with pytest.raises(FileNotFoundError, match="No objects found"):
        feeder.list_s3_keys(bucket=s3_bucket, prefix="nothing/here")

@pytest.mark.parametrize(
    ("s3_objects", "batched_s3_keys", "expected_files"),
    [
        pytest.param(
            {"prefix/one.jsonl": b'{"id": 1}\n'},
            ["prefix/one.jsonl"],
            {"one.jsonl": [{"id": 1}]},
            id="one-key",
        ),
        pytest.param(
            {
                "prefix/one.jsonl": b'{"id": 1}\n',
                "prefix/two.jsonl": b'{"id": 2}\n{"id": 3}\n',
            },
            ["prefix/one.jsonl", "prefix/two.jsonl"],
            {"one.jsonl": [{"id": 1}], "two.jsonl": [{"id": 2}, {"id": 3}]},
            id="one-file-per-key",
        ),
        pytest.param(
            {"a/deep/prefix/one.jsonl": b'{"id": 1}\n'},
            ["a/deep/prefix/one.jsonl"],
            {"one.jsonl": [{"id": 1}]},
            id="named-after-the-key-basename",
        ),
        pytest.param({}, [], {}, id="no-keys"),
    ],
)
def test_materialise_s3_files_writes_one_file_per_key(
    s3_client, s3_bucket, tmp_path, s3_objects, batched_s3_keys, expected_files
):
    put_s3_objects(s3_client, s3_bucket, s3_objects)

    paths = feeder.materialise_s3_files(
        bucket=s3_bucket, batched_s3_keys=batched_s3_keys, materialise_dir=tmp_path
    )

    assert paths == [tmp_path / name for name in expected_files]
    assert {path.name: read_jsonl(path) for path in paths} == expected_files

@pytest.mark.parametrize(
    ("sources", "derive_data_from_source", "expected_files"),
    [
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}, {"id": 2}]},
            id="no-deriver",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n{"id": 2}\n'},
            lambda record: record | {"derived": True},
            {
                "one.derived.jsonl": [
                    {"id": 1, "derived": True},
                    {"id": 2, "derived": True},
                ]
            },
            id="deriver-applied-to-every-record",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n\n\n{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}, {"id": 2}]},
            id="blank-lines-skipped",
        ),
        pytest.param(
            {"one.jsonl": b'{"id": 1}\n', "two.jsonl": b'{"id": 2}\n'},
            None,
            {"one.derived.jsonl": [{"id": 1}], "two.derived.jsonl": [{"id": 2}]},
            id="one-derived-file-per-source",
        ),
        pytest.param(
            {"one.jsonl": b""}, None, {"one.derived.jsonl": []}, id="empty-source"
        ),
    ],
)
def test_materialise_derived_files_writes_a_new_file_per_source(
    tmp_path, sources, derive_data_from_source, expected_files
):
    """
    Every case must leave the sources on disk and untouched.

    `feed_batch` deletes the sources the moment this returns, so handing them
    back instead of new files would delete the files about to be fed.
    """
    source_paths = []
    for name, content in sources.items():
        source_path = tmp_path / name
        source_path.write_bytes(content)
        source_paths.append(source_path)

    derived = feeder.materialise_derived_files(
        materialised_s3_files=source_paths,
        derive_data_from_source=derive_data_from_source,
    )

    assert derived == [tmp_path / name for name in expected_files]
    assert {path.name: read_jsonl(path) for path in derived} == expected_files
    assert {path.name: path.read_bytes() for path in source_paths} == sources

@pytest.mark.parametrize(
    ("present", "absent"),
    [
        pytest.param(["one.jsonl"], [], id="present"),
        pytest.param([], ["gone.jsonl"], id="already-missing"),
        pytest.param(["one.jsonl", "two.jsonl"], ["gone.jsonl"], id="mixed"),
        pytest.param([], [], id="nothing-to-delete"),
    ],
)
def test_delete_materialised_s3_files_removes_every_file_it_is_given(
    tmp_path, present, absent
):
    paths = [write_jsonl(tmp_path / name, [{"id": 1}]) for name in present]
    paths += [tmp_path / name for name in absent]

    feeder.delete_materialised_s3_files(paths)

    assert list(tmp_path.iterdir()) == []
