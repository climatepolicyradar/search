"""
Snowflake access for document-topic relevance enrichment.

Fetches passage-level mentions of each topic within each document from the data
warehouse, so the predictors can compute signals like mention count, density,
mentions-per-page and positional features.

Local-only: connects via the `local_dev` connection profile in
`~/.snowflake/connections.toml`. Mirrors the local path of the knowledge-graph
`build_dataset.py` pattern, without the production key-pair branch.
"""

from collections import defaultdict

import snowflake.connector

from research.document_topic_relevance.src.models import TopicMention, TopicMentions

# Tables queried (see eval_set_selection.sql for the same sources).
PASSAGES_TABLE = "production.published.PIPELINE_PASSAGES_V1"
TOPICS_TABLE = "production.playground.UNIFIED_PASSAGE_TOPICS"
# Passage TYPE that marks the start of a new section; a section is the run of passages
# from one heading to the next.
SECTION_HEADING_TYPE = "sectionHeading"


def connect() -> snowflake.connector.SnowflakeConnection:
    """Connect using the local `local_dev` connection profile."""
    return snowflake.connector.connect(connection_name="local_dev")


def _in_list(values: list[str]) -> tuple[str, list[str]]:
    """Build a parameterized `(?, ?, ...)` placeholder list and its bind values."""
    placeholders = ", ".join(["%s"] * len(values))
    return f"({placeholders})", list(values)


def fetch_topic_mentions(
    conn: snowflake.connector.SnowflakeConnection,
    doc_ids: list[str],
    topic_names: list[str],
) -> dict[tuple[str, str], TopicMentions]:
    """
    Fetch passage-level topic mentions for the given documents and topics.

    Returns a mapping keyed by `(document_id, lower(trim(topic_name)))`. The topic
    key is lower-cased and trimmed to match `Label.value` against the warehouse's
    `TOPIC_NAME`. Documents present in `doc_ids` but with no mentions of a topic
    simply don't appear under that key – callers should default to an empty
    `TopicMentions` with the document's `total_passages`.

    Three queries are run and assembled in Python:
      1. per-document passage totals and max page number,
      2. per-section passage counts (a section = the run of passages between
         `sectionHeading` blocks, numbered by a running count over reading order),
      3. per (document, topic) the page number, reading-order index and section of
         each mentioning passage.
    """
    if not doc_ids or not topic_names:
        return {}

    cur = conn.cursor()
    doc_ph, doc_binds = _in_list(doc_ids)
    topic_ph, topic_binds = _in_list([t.lower().strip() for t in topic_names])

    # Assigns each passage a SECTION_ID = running count of section headings seen so far
    # in reading order. Reused by the section-size and mention queries below.
    sectioned_cte = f"""
        WITH sectioned AS (
            SELECT
                DOCUMENT_ID,
                TEXT_BLOCK_ID,
                PAGE_NUMBER,
                SUM(CASE WHEN TYPE = '{SECTION_HEADING_TYPE}' THEN 1 ELSE 0 END) OVER (
                    PARTITION BY DOCUMENT_ID
                    ORDER BY TRY_CAST(TEXT_BLOCK_ID AS INT)
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS SECTION_ID
            FROM {PASSAGES_TABLE}
            WHERE DOCUMENT_ID IN {doc_ph}
        )
    """

    # 1. Per-document passage totals and page length.
    cur.execute(
        f"""
        SELECT DOCUMENT_ID,
               COUNT(*)         AS TOTAL_PASSAGES,
               MAX(PAGE_NUMBER) AS MAX_PAGE
        FROM {PASSAGES_TABLE}
        WHERE DOCUMENT_ID IN {doc_ph}
        GROUP BY DOCUMENT_ID
        """,
        doc_binds,
    )
    stats: dict[str, tuple[int, int | None]] = {
        row[0]: (int(row[1]), int(row[2]) if row[2] is not None else None)
        for row in cur.fetchall()
    }

    # 2. Per-section passage counts.
    cur.execute(
        sectioned_cte
        + """
        SELECT DOCUMENT_ID, SECTION_ID, COUNT(*) AS SECTION_PASSAGES
        FROM sectioned
        GROUP BY DOCUMENT_ID, SECTION_ID
        """,
        doc_binds,
    )
    section_sizes_by_doc: dict[str, dict[int, int]] = defaultdict(dict)
    for document_id, section_id, section_passages in cur.fetchall():
        section_sizes_by_doc[document_id][int(section_id)] = int(section_passages)

    # 2b. Per-page passage counts (denominator for first-n-pages density).
    cur.execute(
        f"""
        SELECT DOCUMENT_ID, PAGE_NUMBER, COUNT(*) AS PAGE_PASSAGES
        FROM {PASSAGES_TABLE}
        WHERE DOCUMENT_ID IN {doc_ph}
          AND PAGE_NUMBER IS NOT NULL
        GROUP BY DOCUMENT_ID, PAGE_NUMBER
        """,
        doc_binds,
    )
    pages_by_doc: dict[str, dict[int, int]] = defaultdict(dict)
    for document_id, page_number, page_passages in cur.fetchall():
        pages_by_doc[document_id][int(page_number)] = int(page_passages)

    # 3. Per (document, topic) mention positions.
    #    PASSAGE_ID joins to TEXT_BLOCK_ID; TEXT_BLOCK_ID is the reading-order index.
    cur.execute(
        sectioned_cte
        + f"""
        SELECT t.DOCUMENT_ID,
               LOWER(TRIM(t.TOPIC_NAME))        AS TOPIC_NAME,
               TRY_CAST(s.TEXT_BLOCK_ID AS INT) AS PASSAGE_INDEX,
               s.PAGE_NUMBER                    AS PAGE_NUMBER,
               s.SECTION_ID                     AS SECTION_ID
        FROM {TOPICS_TABLE} t
        JOIN sectioned s
          ON t.DOCUMENT_ID = s.DOCUMENT_ID
         AND t.PASSAGE_ID = s.TEXT_BLOCK_ID
        WHERE LOWER(TRIM(t.TOPIC_NAME)) IN {topic_ph}
        """,
        doc_binds + topic_binds,
    )

    mentions_by_pair: dict[tuple[str, str], list[TopicMention]] = defaultdict(list)
    for (
        document_id,
        topic_name,
        passage_index,
        page_number,
        section_id,
    ) in cur.fetchall():
        if passage_index is None:
            continue
        mentions_by_pair[(document_id, topic_name)].append(
            TopicMention(
                passage_index=int(passage_index),
                page_number=int(page_number) if page_number is not None else None,
                section_id=int(section_id) if section_id is not None else None,
            )
        )

    result: dict[tuple[str, str], TopicMentions] = {}
    for (document_id, topic_name), mentions in mentions_by_pair.items():
        total_passages, max_page = stats.get(document_id, (0, None))
        doc_sections = section_sizes_by_doc.get(document_id, {})
        used = {m.section_id for m in mentions if m.section_id is not None}
        section_sizes = {s: doc_sections[s] for s in used if s in doc_sections}
        result[(document_id, topic_name)] = TopicMentions(
            total_passages=total_passages,
            max_page=max_page,
            mentions=sorted(mentions, key=lambda m: m.passage_index),
            section_sizes=section_sizes,
            passages_per_page=dict(pages_by_doc.get(document_id, {})),
        )

    return result
