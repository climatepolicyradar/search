from prefect import flow
from search.vespa.documents_feed_materializer import (
    documents_concepts_feed_materializer,
    documents_feed_materializer,
)


@flow(log_prints=True)
def documents_feed_flow():
    documents_feed_materializer()
    documents_concepts_feed_materializer()
