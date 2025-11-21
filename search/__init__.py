from search.document import Document
from search.label import Label
from search.passage import Passage

SearchResult = Label | Passage | Document
