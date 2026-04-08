from search.engines import OrderBy, Pagination
from search.log import get_logger

logger = get_logger(__name__)


def pagination(page_token: int = 1, page_size: int = 10):
    """
    Shared pagination parameters

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see:https://google.aip.dev/158
    """
    return Pagination(page_token=page_token, page_size=page_size)


def order_by(order_by: str = "relevance desc"):
    """
    Shared order by parameters

    @see: https://fastapi.tiangolo.com/tutorial/dependencies/#import-depends
    @see: https://google.aip.dev/132#ordering
    """

    order_by_list: list[OrderBy] = []
    for order_by_tuple in order_by.split(","):
        field, direction = order_by_tuple.split(" ")
        order_by_list.append(OrderBy(field=field, direction=direction or "desc"))
    return order_by_list
