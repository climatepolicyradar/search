USE DATABASE production;
USE SCHEMA playground;

-- ============================================================================
-- EVAL SET: TOPIC → DOCUMENT RELEVANCE
-- ============================================================================
-- HOW RANDOM SELECTION WORKS
-- ─────────────────────────────────────────────────────────────────────────────
-- Many documents will qualify for a given slot (e.g. hundreds of docs are in
-- the top-10% for a popular topic like "tax"). We want to pick ONE at random,
-- not always the same one.
--
-- The trick is ROW_NUMBER() OVER (PARTITION BY ... ORDER BY RANDOM()).
-- Think of it like shuffling a deck of cards within each group: Snowflake
-- assigns each qualifying row a fresh random number, then we keep the one
-- that ended up on top (rn = 1). Re-running the script picks a different card.
--
-- For Tier 1, the pool is deliberately narrow (top-10% only), so the randomly
-- chosen document is still guaranteed to be a strong example of that topic.
-- ============================================================================
-- TODOs before first run:
--   1. Verify topic root names — run TEST 2b below first
--   2. Verify corpus name strings — run TEST 4 below first
-- ============================================================================


-- ============================================================================
-- STEP 1: per-document passage totals and page length
-- ============================================================================
-- Scans PIPELINE_PASSAGES_V1 once; reused by all later steps.

CREATE OR REPLACE TABLE EVAL_DOC_STATS AS
SELECT
    DOCUMENT_ID,
    COUNT(*)         AS TOTAL_PASSAGES,
    MAX(PAGE_NUMBER) AS MAX_PAGE
FROM published.PIPELINE_PASSAGES_V1
GROUP BY DOCUMENT_ID;

-- TEST 1: shape check — expect thousands of docs, MAX_PAGE in a plausible range
SELECT
    COUNT(*)                             AS total_docs,
    MIN(MAX_PAGE)                        AS min_pages,
    MAX(MAX_PAGE)                        AS max_pages,
    MEDIAN(MAX_PAGE)                     AS median_pages,
    COUNT_IF(MAX_PAGE < 5)               AS short_count,
    COUNT_IF(MAX_PAGE BETWEEN 40 AND 60) AS medium_count,
    COUNT_IF(MAX_PAGE > 200)             AS long_count
FROM EVAL_DOC_STATS;


-- ============================================================================
-- STEP 2: passage counts per document × eval topic, plus percentile ranks
-- ============================================================================
-- ABS_PRANK = where this doc sits vs all others for this topic by raw count
--             (0 = fewest, 1 = most). Top-10% means ABS_PRANK >= 0.9.
-- REL_PRANK = same but for share of doc's own passages — favours short docs
--             where a topic is central, not just long docs that mention everything.

CREATE OR REPLACE TABLE EVAL_DOC_TOPIC_RANKED AS
WITH eval_topics (TOPIC) AS (
    SELECT LOWER(TRIM(t)) FROM (VALUES
        ('emissions reduction target'),
        ('tax'),
        ('zoning and spatial planning'),
        ('adaptation'),               -- TODO: verify root label (see TEST 2b)
        ('freshwater adaptation'),
        ('cryosphere risk'),
        ('heavy precipitation'),
        ('women and minority genders'),
        ('people on the move'),
        ('green jobs'),
        ('renewable energy'),         -- TODO: verify root label
        ('marine energy'),
        ('greenhouse gas'),           -- TODO: verify root label
        ('methane'),
        ('finance flow'),
        ('loss and damage finance')
    ) t(t)
),
doc_topic_counts AS (
    SELECT
        pt.DOCUMENT_ID,
        LOWER(TRIM(pt.TOPIC_NAME)) AS TOPIC_NAME,
        COUNT(*)                   AS TOPIC_PASSAGES
    FROM UNIFIED_PASSAGE_TOPICS pt
    WHERE LOWER(TRIM(pt.TOPIC_NAME)) IN (SELECT TOPIC FROM eval_topics)
    GROUP BY pt.DOCUMENT_ID, LOWER(TRIM(pt.TOPIC_NAME))
)
SELECT
    dtc.DOCUMENT_ID,
    dtc.TOPIC_NAME,
    dtc.TOPIC_PASSAGES,
    ds.TOTAL_PASSAGES,
    dtc.TOPIC_PASSAGES / NULLIF(ds.TOTAL_PASSAGES, 0) AS REL_FREQ,
    PERCENT_RANK() OVER (
        PARTITION BY dtc.TOPIC_NAME
        ORDER BY dtc.TOPIC_PASSAGES
    ) AS ABS_PRANK,
    PERCENT_RANK() OVER (
        PARTITION BY dtc.TOPIC_NAME
        ORDER BY dtc.TOPIC_PASSAGES / NULLIF(ds.TOTAL_PASSAGES, 0)
    ) AS REL_PRANK
FROM doc_topic_counts dtc
JOIN EVAL_DOC_STATS ds ON dtc.DOCUMENT_ID = ds.DOCUMENT_ID;

-- TEST 2a: spot-check a rare topic — expect rows with ABS_PRANK near 1.0 at the top
SELECT TOPIC_NAME, TOPIC_PASSAGES, TOTAL_PASSAGES, ROUND(REL_FREQ, 4) AS REL_FREQ,
       ROUND(ABS_PRANK, 3) AS ABS_PRANK, ROUND(REL_PRANK, 3) AS REL_PRANK
FROM EVAL_DOC_TOPIC_RANKED
WHERE TOPIC_NAME = 'loss and damage finance'
ORDER BY TOPIC_PASSAGES DESC
LIMIT 5;

-- TEST 2b: which topic names actually matched? (0 rows for a topic = wrong label)
--          Also use this to verify the three root names marked TODO above.
SELECT TOPIC_NAME, COUNT(DISTINCT DOCUMENT_ID) AS docs_with_topic
FROM EVAL_DOC_TOPIC_RANKED
GROUP BY TOPIC_NAME
ORDER BY TOPIC_NAME;


-- ============================================================================
-- STEP 3: Tier 1 — topic coverage (up to 32 documents)
-- ============================================================================
-- For each topic, randomly pick 1 document from its top-10% pool.
-- Done twice: once for absolute count, once for relative frequency.

CREATE OR REPLACE TABLE EVAL_TIER1 AS
SELECT DOCUMENT_ID, 'tier1_absolute:' || TOPIC_NAME AS SELECTION_REASON
FROM (
    SELECT DOCUMENT_ID, TOPIC_NAME,
           ROW_NUMBER() OVER (PARTITION BY TOPIC_NAME ORDER BY RANDOM()) AS rn
    FROM EVAL_DOC_TOPIC_RANKED
    WHERE ABS_PRANK >= 0.9
)
WHERE rn = 1

UNION ALL

SELECT DOCUMENT_ID, 'tier1_relative:' || TOPIC_NAME AS SELECTION_REASON
FROM (
    SELECT DOCUMENT_ID, TOPIC_NAME,
           ROW_NUMBER() OVER (PARTITION BY TOPIC_NAME ORDER BY RANDOM()) AS rn
    FROM EVAL_DOC_TOPIC_RANKED
    WHERE REL_PRANK >= 0.9
)
WHERE rn = 1;

-- TEST 3: expect 16 selections per method; fewer unique docs than 32 is fine
--         (means one doc was a top example for multiple topics)
SELECT
    LEFT(SELECTION_REASON, CHARINDEX(':', SELECTION_REASON) - 1) AS METHOD,
    COUNT(*)                  AS selections,
    COUNT(DISTINCT DOCUMENT_ID) AS unique_docs
FROM EVAL_TIER1
GROUP BY 1;


-- ============================================================================
-- STEP 4: document metadata (base for diversity tiers)
-- ============================================================================

CREATE OR REPLACE TABLE EVAL_DOC_META AS
SELECT
    d.DOCUMENT_ID,
    COALESCE(d.METADATA_CORPUS_TYPE_NAME, d.METADATA_CATEGORY, 'Unknown') AS CORPUS,
    d.DOCUMENT_NAME,
    d.DOCUMENT_SLUG,
    d.METADATA_GEOGRAPHIES,
    ds.MAX_PAGE
FROM published.PIPELINE_DOCUMENTS_V1 d
JOIN EVAL_DOC_STATS ds ON d.DOCUMENT_ID = ds.DOCUMENT_ID
WHERE d.IS_PUBLISHED = TRUE
  AND d.PUBLISHED_DATE IS NOT NULL;

-- TEST 4: corpus distribution — use this output to verify the strings in Step 5's CASE
SELECT CORPUS, COUNT(*) AS doc_count
FROM EVAL_DOC_META
GROUP BY CORPUS
ORDER BY doc_count DESC
LIMIT 15;


-- ============================================================================
-- STEP 5: Tier 2 — corpus diversity (7 documents)
-- ============================================================================
-- Only adds documents not already in Tier 1.
-- Quotas: UNCBD ×1, UNCCD ×1, Litigation ×2, Laws and Policies ×2, MCF ×1.

CREATE OR REPLACE TABLE EVAL_TIER2 AS
SELECT DOCUMENT_ID, 'tier2_corpus:' || CORPUS AS SELECTION_REASON
FROM (
    SELECT
        DOCUMENT_ID,
        CORPUS,
        CASE CORPUS
            WHEN 'UNCBD'             THEN 1
            WHEN 'UNCCD'             THEN 1
            WHEN 'Litigation'        THEN 2
            WHEN 'Laws and Policies' THEN 2
            WHEN 'MCF'               THEN 1
        END AS QUOTA,
        ROW_NUMBER() OVER (PARTITION BY CORPUS ORDER BY RANDOM()) AS rn
    FROM EVAL_DOC_META
    WHERE DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER1)
      AND CORPUS IN ('UNCBD', 'UNCCD', 'Litigation', 'Laws and Policies', 'MCF')
)
WHERE rn <= QUOTA;

-- TEST 5: expect 1 row for UNCBD/UNCCD/MCF, 2 rows for Litigation/Laws and Policies
--         missing rows = corpus name mismatch (fix in CASE above)
SELECT SELECTION_REASON, COUNT(*) AS selected
FROM EVAL_TIER2
GROUP BY SELECTION_REASON
ORDER BY SELECTION_REASON;


-- ============================================================================
-- STEP 6: Tier 3 — document length diversity (6 documents)
-- ============================================================================
-- 2 docs per length band, randomly picked from those not yet selected.

CREATE OR REPLACE TABLE EVAL_TIER3 AS
SELECT DOCUMENT_ID, 'tier3_length:' || LENGTH_BAND AS SELECTION_REASON
FROM (
    SELECT
        DOCUMENT_ID,
        LENGTH_BAND,
        ROW_NUMBER() OVER (PARTITION BY LENGTH_BAND ORDER BY RANDOM()) AS rn
    FROM (
        SELECT
            DOCUMENT_ID,
            CASE
                WHEN MAX_PAGE > 200             THEN 'long'
                WHEN MAX_PAGE BETWEEN 40 AND 60 THEN 'medium'
                WHEN MAX_PAGE < 5               THEN 'short'
            END AS LENGTH_BAND
        FROM EVAL_DOC_META
        WHERE DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER1)
          AND DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER2)
          AND MAX_PAGE IS NOT NULL
    )
    WHERE LENGTH_BAND IS NOT NULL
)
WHERE rn <= 2;

-- TEST 6: expect 2 rows per band; a missing band means no unselected docs in that range
SELECT SELECTION_REASON, COUNT(*) AS selected
FROM EVAL_TIER3
GROUP BY SELECTION_REASON
ORDER BY SELECTION_REASON;


-- ============================================================================
-- STEP 7: Tier 4 — geography diversity (5 documents)
-- ============================================================================
-- Assigns each document its primary region, counts how many already-selected
-- docs come from each region, then adds 1 random doc from each of the 5 most
-- under-represented regions.

CREATE OR REPLACE TABLE EVAL_DOC_REGIONS AS
SELECT dm.DOCUMENT_ID, COALESCE(igl.REGION, 'International') AS REGION
FROM EVAL_DOC_META dm
JOIN published.PIPELINE_DOCUMENTS_V1 d ON dm.DOCUMENT_ID = d.DOCUMENT_ID
LEFT JOIN LATERAL FLATTEN(input => d.METADATA_GEOGRAPHIES, outer => true) geo
LEFT JOIN production.playground.ISO_GEO_LOOKUP igl ON geo.value::STRING = igl.ALPHA3
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY dm.DOCUMENT_ID
    ORDER BY igl.REGION NULLS LAST
) = 1;

-- TEST 7a: region distribution across all docs — context for what's under-represented
SELECT REGION, COUNT(*) AS doc_count
FROM EVAL_DOC_REGIONS
GROUP BY REGION
ORDER BY doc_count DESC;

CREATE OR REPLACE TABLE EVAL_TIER4 AS
WITH selected_region_counts AS (
    SELECT dr.REGION, COUNT(DISTINCT dr.DOCUMENT_ID) AS CNT
    FROM EVAL_DOC_REGIONS dr
    WHERE dr.DOCUMENT_ID IN (
        SELECT DOCUMENT_ID FROM EVAL_TIER1
        UNION ALL SELECT DOCUMENT_ID FROM EVAL_TIER2
        UNION ALL SELECT DOCUMENT_ID FROM EVAL_TIER3
    )
    GROUP BY dr.REGION
)
SELECT DOCUMENT_ID, 'tier4_geography:' || REGION AS SELECTION_REASON
FROM (
    SELECT
        dr.DOCUMENT_ID,
        dr.REGION,
        ROW_NUMBER() OVER (PARTITION BY dr.REGION ORDER BY RANDOM()) AS rn_in_region,
        DENSE_RANK()  OVER (ORDER BY COALESCE(src.CNT, 0), dr.REGION) AS region_priority
    FROM EVAL_DOC_REGIONS dr
    LEFT JOIN selected_region_counts src ON dr.REGION = src.REGION
    WHERE dr.DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER1)
      AND dr.DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER2)
      AND dr.DOCUMENT_ID NOT IN (SELECT DOCUMENT_ID FROM EVAL_TIER3)
)
WHERE rn_in_region = 1
  AND region_priority <= 5;

-- TEST 7b: which regions were added to fill gaps?
SELECT SELECTION_REASON FROM EVAL_TIER4 ORDER BY 1;


-- ============================================================================
-- STEP 8: final table — union all tiers, deduplicate, attach metadata
-- ============================================================================

CREATE OR REPLACE TABLE EVAL_SET_DOCUMENTS AS
WITH all_tiers AS (
    SELECT DOCUMENT_ID, SELECTION_REASON FROM EVAL_TIER1
    UNION ALL
    SELECT DOCUMENT_ID, SELECTION_REASON FROM EVAL_TIER2
    UNION ALL
    SELECT DOCUMENT_ID, SELECTION_REASON FROM EVAL_TIER3
    UNION ALL
    SELECT DOCUMENT_ID, SELECTION_REASON FROM EVAL_TIER4
)
SELECT
    a.DOCUMENT_ID,
    dm.DOCUMENT_NAME,
    dm.DOCUMENT_SLUG,
    dm.CORPUS,
    dm.MAX_PAGE,
    LISTAGG(a.SELECTION_REASON, ' | ') WITHIN GROUP (ORDER BY a.SELECTION_REASON) AS SELECTION_REASONS,
    (
        SELECT LISTAGG(COALESCE(igl2.REGION, 'Unknown'), ', ')
               WITHIN GROUP (ORDER BY igl2.REGION NULLS LAST)
        FROM published.PIPELINE_DOCUMENTS_V1 d2
        LEFT JOIN LATERAL FLATTEN(input => d2.METADATA_GEOGRAPHIES, outer => true) geo2
        LEFT JOIN production.playground.ISO_GEO_LOOKUP igl2 ON geo2.value::STRING = igl2.ALPHA3
        WHERE d2.DOCUMENT_ID = a.DOCUMENT_ID
    ) AS REGIONS
FROM all_tiers a
JOIN EVAL_DOC_META dm ON a.DOCUMENT_ID = dm.DOCUMENT_ID
GROUP BY a.DOCUMENT_ID, dm.DOCUMENT_NAME, dm.DOCUMENT_SLUG, dm.CORPUS, dm.MAX_PAGE
ORDER BY MIN(LEFT(a.SELECTION_REASON, 5)), a.DOCUMENT_ID;

-- TEST 8: final count and tier breakdown — total should be ≤50
SELECT
    CASE
        WHEN SELECTION_REASONS LIKE 'tier1%' THEN 'tier1 (topic coverage)'
        WHEN SELECTION_REASONS LIKE 'tier2%' THEN 'tier2 (corpus)'
        WHEN SELECTION_REASONS LIKE 'tier3%' THEN 'tier3 (length)'
        ELSE 'tier4 (geography)'
    END AS PRIMARY_TIER,
    COUNT(*) AS docs
FROM EVAL_SET_DOCUMENTS
GROUP BY 1
ORDER BY 1;

SELECT * FROM EVAL_SET_DOCUMENTS ORDER BY SELECTION_REASONS, DOCUMENT_ID;
