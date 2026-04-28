from prefect import flow, task
from search.vespa.documents_feed_materializer import (
    documents_concepts_feed_materializer,
    documents_feed_materializer,
    documents_passages_feed_materializer,
    documents_principal_concepts_feed_materializer,
    documents_principal_passages_feed_materializer,
)


@task
def run_documents_feed_materializer():
    documents_feed_materializer()


@task
def run_documents_concepts_feed_materializer():
    documents_concepts_feed_materializer()


@task
def run_documents_passages_feed_materializer():
    documents_passages_feed_materializer()


@task
def run_documents_principal_passages_feed_materializer():
    documents_principal_passages_feed_materializer()


@task
def run_documents_principal_concepts_feed_materializer():
    documents_principal_concepts_feed_materializer()


@flow(log_prints=True)
def documents_feed_flow():
    run_documents_feed_materializer()
    run_documents_concepts_feed_materializer()
    run_documents_passages_feed_materializer()
    run_documents_principal_passages_feed_materializer()
    run_documents_principal_concepts_feed_materializer()
