from prefect import flow
from search.vespa.labels_feed import labels_feed_materializer


@flow(log_prints=True)
def labels_feed_flow():
    labels_feed_materializer()
