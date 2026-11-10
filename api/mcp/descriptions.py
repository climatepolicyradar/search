"""
Everything the model reads when choosing a tool.

This wording decides which tool Claude picks, so re-test from Claude after
changing it. It's sent on every turn, so say each thing once.
"""

INSTRUCTIONS = (
    "Search Climate Policy Radar's database of climate laws, policies, court "
    "cases, reports and UN submissions, ranked the same way as the CPR website. "
    "Use these tools to find documents on a topic and to find or quote what they "
    "say. They return the best matches, not every match, so they are not for "
    "counting or listing everything. For counts, totals or full lists, use the "
    "CPR data lake MCP instead. When you answer, only attribute to CPR what "
    "these tools returned. If you add anything from your own knowledge, such as "
    "a later amendment or a figure the text doesn't give, say it isn't from CPR."
)

_FILTERS = (
    "Filters narrow the results. Any value within a filter matches, and "
    "different filters must all match."
)

SEARCH_DOCUMENTS = (
    "Find climate laws, policies, court cases and other documents, one result "
    "per law, policy or case. E.g. 'which policies in Kenya cover adaptation "
    "finance'. For a broad theme use topics. For a narrower subject, get its id "
    f"from find_concepts and pass it as concepts. {_FILTERS} To read or quote a "
    "document, pass its id to search_passages."
)

SEARCH_PASSAGES = (
    "Find passages of text to quote or cite, e.g. 'what does Kenya's climate "
    "act say about adaptation finance'. Pass document_ids to search inside "
    f"documents from search_documents. {_FILTERS} Long passages are cut, end "
    "in '…' and have text_truncated set. Call get_passage before quoting or "
    "summarising one. Text is matched by its words. Most text is in English, "
    "including translations, so search in English first. If that finds nothing "
    "relevant in a document, it may be in its original language, so try that."
)

GET_PASSAGE = (
    "Read one passage in full, with the passages before and after it. Use this "
    "when a passage is text_truncated, or to see the text around a quote."
)

FIND_CONCEPTS = (
    "Look up CPR's curated concepts, e.g. 'just transition', to get ids for the "
    "concepts filter. More precise than putting the subject in the query, "
    "because it only matches text tagged with that concept. If nothing fits, "
    "leave concepts out and put the subject in the query."
)

GET_DOCUMENT = (
    "Look up one document by id, e.g. a passage's document_id. is_principal "
    "is true for a law, policy or case itself, and false for one of its "
    "versions or filings."
)

QUERY = "What to search for, in plain words."
GEOGRAPHIES = "Countries, as ISO 3166-1 alpha-3 codes, e.g. ['KEN', 'GBR']."
CATEGORIES = "Kinds of document."
TOPICS = (
    "Broad themes. Only laws and policies are tagged, so this leaves out other "
    "kinds of document."
)
CONCEPTS = (
    "Concept ids from find_concepts, e.g. ['concept::Q1343']. Tagging isn't "
    "exhaustive, so if this returns little, try a broader concept or drop it."
)
REGIONS = (
    "World Bank regions. For other groups, like small island states, list their "
    "countries in geographies."
)
TEXT_BLOCK_ID = "A text_block_id from search_passages."
CONTEXT = "How many passages to include before and after it."
CONCEPT_QUERY = "The subject to look up, in plain words."
PUBLISHED_AFTER = "Published on or after this date."
PUBLISHED_BEFORE = "Published on or before this date."
DOCUMENT_IDS = (
    "Ids from search_documents. A law's id covers all its versions. Can't be "
    "combined with other filters."
)
DOCUMENT_ID = "A document id, e.g. 'CCLW.family.2042.0'."
LIMIT = (
    "How many results to return. has_more means there are more matches, so the "
    "number of results is never a total."
)
CONCEPT_LIMIT = "How many concepts to return."
