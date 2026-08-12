"""TODO: this is temporary - https://linear.app/climate-policy-radar/issue/FUS-238/remove-temporary-data-in-pipelines-labels-vespa-materializer-and"""

import itertools
from collections.abc import Iterator

import httpx
from cpr_contracts import Label


def read() -> Iterator[Label]:
    """Yield every label from the data-in API, a page at a time until one comes back empty."""
    with httpx.Client(timeout=30) as client:
        for page in itertools.count(1):
            response = client.get(
                "https://api.climatepolicyradar.org/data-in/labels",
                params={"page": page},
            )
            response.raise_for_status()

            labels = response.json()["data"]
            if not labels:
                return

            print(f"Read {len(labels)} labels from page {page}.")
            for label in labels:
                yield Label.model_validate(label)
