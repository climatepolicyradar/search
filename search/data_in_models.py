"""
Taken from the upstream data-in-api.

@see: https://github.com/climatepolicyradar/navigator-backend/blob/main/data-in-models/src/data_in_models/models.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WithRelationships(BaseModel):
    labels: list[LabelRelationship] = []
    documents: list[DocumentRelationship] = []


class Attribute(BaseModel):
    type: str
    value: str | float | bool


class WithAttributes(BaseModel):
    # the `key` of the `dict` will probably be managed via our knowledge managers
    # and not be a free for all
    attributes: dict[str, Attribute] = {}


class Label(BaseModel):
    id: str
    type: str
    value: str


class LabelRelationship(BaseModel):
    type: str
    value: Label
    timestamp: datetime | None = None


class Item(BaseModel):
    url: str | None = None


class BaseDocument(WithAttributes):
    id: str
    title: str
    description: str | None = None
    items: list[Item] = []


class DocumentRelationship(BaseModel):
    type: str
    value: DocumentWithoutRelationships
    timestamp: datetime | None = None


class Document(BaseDocument, WithRelationships):
    pass


class DocumentWithoutRelationships(BaseDocument):
    labels: list[LabelRelationship] = []
