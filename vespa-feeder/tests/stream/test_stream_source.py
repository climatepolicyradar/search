import pytest
from helpers import put_s3_objects
from mypy_boto3_s3 import S3Client
from stream.source import S3Source


def test_s3_source_reads_only_the_newest_export(
    s3_client: S3Client,
    s3_bucket: str,
) -> None:
    put_s3_objects(
        s3_client=s3_client,
        bucket=s3_bucket,
        objects={
            "p/20260101T000000Z/part-0.jsonl": b'{"export": "old"}\n',
            "p/20260922T190625Z/part-0.jsonl": b'{"export": "new"}\n',
            "p/latest/part-0.jsonl": b'{"export": "latest"}\n',
        },
    )
    assert list(S3Source(bucket=s3_bucket, prefix="p/").lines()) == [{"export": "new"}]


def test_s3_source_reads_every_line_of_every_object(
    s3_client: S3Client,
    s3_bucket: str,
) -> None:
    put_s3_objects(
        s3_client=s3_client,
        bucket=s3_bucket,
        objects={
            "p/20260922T190625Z/part-0.jsonl": b'{"i": 0}\n{"i": 1}\n',
            "p/20260922T190625Z/part-1.jsonl": b'{"i": 2}\n',
        },
    )
    expected = [{"i": 0}, {"i": 1}, {"i": 2}]
    assert list(S3Source(bucket=s3_bucket, prefix="p/").lines()) == expected


def test_s3_source_raises_without_a_timestamped_export(
    s3_client: S3Client,
    s3_bucket: str,
) -> None:
    put_s3_objects(
        s3_client=s3_client,
        bucket=s3_bucket,
        objects={"p/latest/part-0.jsonl": b"{}\n"},
    )
    with pytest.raises(FileNotFoundError):
        list(S3Source(bucket=s3_bucket, prefix="p/").lines())


def test_s3_source_skips_blank_lines(s3_client: S3Client, s3_bucket: str) -> None:
    objects = {"p/20260922T190625Z/part-0.jsonl": b'{"i": 0}\n\n{"i": 1}\n\n'}
    put_s3_objects(s3_client=s3_client, bucket=s3_bucket, objects=objects)
    expected = [{"i": 0}, {"i": 1}]
    assert list(S3Source(bucket=s3_bucket, prefix="p/").lines()) == expected
