from abc import ABC, abstractmethod

from research.document_topic_relevance.src.models import Score
from search.document import Document
from search.label import Label


class DTPredictor(ABC):
    """
    Predictor for bidirectional relevance between a topic and a document

    Encodes the assumption that if a topic is not mentioned in a document, it cannot
    be relevant – so it has a score of 0.
    """

    def predict(self, document: Document, topic: Label) -> Score:
        """Predict document-topic relevance"""

        if topic.id not in document.labels:
            return 0

        return self._predict(document, topic)

    @abstractmethod
    def _predict(self, document: Document, topic: Label) -> Score:
        raise NotImplementedError()


class AnyMentionIsRelevantPredictor(DTPredictor):
    """All mentions of a topic in a document result in a score of 2."""

    def _predict(self, document: Document, topic: Label) -> Score:  # noqa: ARG002
        return 2
