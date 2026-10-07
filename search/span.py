from pydantic import BaseModel


class BaseSpan[T](BaseModel):
    """A span is a class that allows you to wrap text from start_index:end_index in value T"""

    start_index: int
    end_index: int
    labelled_text: str
    value: T
