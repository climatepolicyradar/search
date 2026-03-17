from typing import TypedDict


class VespaAssign[T](TypedDict):
    assign: T


class VespaUpdate[Fields](TypedDict):
    update: str
    create: bool
    fields: Fields
