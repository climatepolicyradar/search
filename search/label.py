from pydantic import BaseModel, Field


class Label(BaseModel):
    """Base class for a label"""

    id: str = Field(default="")
    type: str = Field(default="")
    value: str = Field(default="")
