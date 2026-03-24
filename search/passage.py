from pydantic import BaseModel, Field, computed_field


class Passage(BaseModel):
    """Base class for a passage"""

    text_block_id: str = Field(default="")
    text: str = Field(default="")
    language: str = Field(default="")
    type: str = Field(default="")
    type_confidence: float = Field(default=0.0)
    page_number: int = Field(default=0)
    heading_id: str | None = Field(default=None)
    document_id: str = Field(default="")

    @computed_field
    @property
    def id(self) -> str:
        """A canonical identifier for the passage."""
        return self.text_block_id
