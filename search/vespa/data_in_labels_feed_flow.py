"""TODO: this is temporary - https://linear.app/climate-policy-radar/issue/FUS-238/remove-temporary-data-in-pipelines-labels-vespa-materializer-and"""

from prefect import flow
from search.vespa.data_in_labels_feed_materializer import (
    data_in_labels_feed_materializer,
)


@flow(log_prints=True)
def data_in_labels_feed_flow():
    data_in_labels_feed_materializer()
