from prefect import flow
from search.vespa.passages_feed_materializer import passages_feed_materializer


@flow(log_prints=True)
def passages_feed_flow():
    passages_feed_materializer()
