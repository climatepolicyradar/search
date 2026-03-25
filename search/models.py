from pydantic import BaseModel


class Pagination(BaseModel):
    """
    Pagination

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see:https://google.aip.dev/158
    """

    page_token: int
    page_size: int
