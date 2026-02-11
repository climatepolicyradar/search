"""
Taken from the upstream data-in-api.

@see: https://github.com/climatepolicyradar/navigator-backend/blob/f12a1bcda05928a731d7a580ea7455eb8d9a7651/data-in-models/src/data_in_models/models.py
"""

from datetime import datetime

from pydantic import BaseModel


class Label(BaseModel):
    id: str
    title: str
    type: str


class DocumentLabelRelationship(BaseModel):
    type: str
    label: Label
    timestamp: datetime | None = None


class Item(BaseModel):
    url: str | None = None


class BaseDocument(BaseModel):
    id: str
    title: str
    description: str | None = None
    labels: list[DocumentLabelRelationship] = []
    items: list[Item] = []


class DocumentDocumentRelationship(BaseModel):
    type: str
    document: "DocumentWithoutRelationships"
    timestamp: datetime | None = None


class Document(BaseDocument):
    relationships: list[DocumentDocumentRelationship] = []


class DocumentWithoutRelationships(BaseDocument):
    pass
