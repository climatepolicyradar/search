from prefect import flow
from search.vespa.data_in_labels_feed_materializer import (
    data_in_labels_feed_materializer,
)


@flow(log_prints=True)
def data_in_labels_feed_flow():
    data_in_labels_feed_materializer()
