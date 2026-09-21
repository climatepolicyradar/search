"""
Acronym candidate pipeline. One command does everything:

    uv run --group research python research/acronyms/run.py

Or a single step:

    ... run.py fetch       Snowflake corpus  -> data/*_candidates.tsv      ~10s
    ... run.py evidence    Snowflake logs    -> data/search_evidence.json  ~2s
    ... run.py workbook    those files       -> data/acronym_candidates.xlsx
    ... run.py sheets      those files       -> data/acronym_candidates_sheets.csv
    ... run.py notion      those files       -> data/acronym_candidates_notion.csv

`fetch` and `evidence` read Snowflake (SELECT only, nothing is written there) and will
pop a browser for SSO. `workbook` is offline, so rerun it freely.

The matcher lives in mine_acronyms.py; check it with `mine_acronyms.py --self-test`.
See README.md for what each step does and how to read the output.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mine_acronyms import (  # noqa: E402
    harvest_parentheticals_text,
    load_blocklist,
    load_stopwords,
)

DATA = Path(__file__).resolve().parent / "data"
MIN_OCCURRENCES = 20

# UNTERM covers all UN work, so a differing expansion nearly always means the letters mean
# something else in another domain (cbd -> cannabidiol), not that our expansion is wrong.
AMBIGUOUS_LABEL = {"Different": "Ambiguous", "Partly": "Ambiguous"}
CPR_HOSTS = {"app.climatepolicyradar.org", "climate-laws.org", "climateprojectexplorer.org"}


def _connect():
    import snowflake.connector
    print("Connecting (a browser window may open for SSO)...", file=sys.stderr)
    return snowflake.connector.connect(connection_name="local_dev")


# ============================================================================
# STEP 1 - find acronym candidates in the corpus
# ============================================================================

TITLES_SQL = r"""
SELECT TITLE
FROM PRODUCTION.PUBLISHED.DOCUMENTS
WHERE REGEXP_LIKE(TITLE, '.*\([A-Z]{2,8}\).*')
"""

# Snowflake's REGEXP_LIKE is implicitly anchored, hence the .* either side above.
# REGEXP_SUBSTR_ALL is not anchored, so the pattern below has no .* padding.
PASSAGES_SQL = r"""
SELECT f.VALUE::STRING AS snippet, COUNT(*) AS n
FROM PRODUCTION.PUBLISHED.PASSAGES_V1,
     LATERAL FLATTEN(INPUT => REGEXP_SUBSTR_ALL(
       TEXT,
       $$[A-Za-z][A-Za-z'-]*( +[A-Za-z][A-Za-z'-]*){1,11} *\([A-Z][A-Za-z0-9+-]{1,7}\)$$
     )) f
GROUP BY 1
HAVING COUNT(*) >= %(min_occurrences)s
ORDER BY n DESC
"""


def write_tsv(expansions: dict[str, Counter], blocked: dict[str, str], path: Path, count_col: str) -> None:
    ready = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["acronym", "expansion", count_col, "status", "note", "rule_line"])
        for acronym, phrases in sorted(expansions.items(), key=lambda kv: sum(kv[1].values()), reverse=True):
            total = sum(phrases.values())
            best = phrases.most_common(1)[0][0]
            if acronym in blocked:
                status, note = "review", blocked[acronym]
            elif len(phrases) > 1:
                variants = "; ".join(f"{p} ({n})" for p, n in phrases.most_common(3))
                status, note = "review", f"competing: {variants}"
            else:
                status, note, ready = "ready", "", ready + 1
            w.writerow([acronym, best, total, status, note, f'{acronym} +> ?"{best}";'])
    print(f"  -> {path.name}: {len(expansions)} acronyms ({ready} ready, {len(expansions) - ready} review)")


def _query(conn, sql: str, params=None) -> list:
    cur = conn.cursor()
    t0 = time.time()
    cur.execute(sql, params or {})
    rows = cur.fetchall()
    print(f"  {len(rows):,} rows in {time.time() - t0:.1f}s")
    return rows


def step_fetch(titles: bool, passages: bool, min_occurrences: int) -> None:
    stopwords, blocked = load_stopwords(), load_blocklist()
    conn = _connect()
    try:
        if titles:
            print("TITLES  PRODUCTION.PUBLISHED.DOCUMENTS")
            exp: defaultdict[str, Counter] = defaultdict(Counter)
            for (title,) in _query(conn, TITLES_SQL):
                for a, ph in harvest_parentheticals_text(str(title or ""), stopwords):
                    exp[a][ph] += 1
            write_tsv(exp, blocked, DATA / "title_candidates.tsv", "titles")
        if passages:
            print(f"PASSAGES  PRODUCTION.PUBLISHED.PASSAGES_V1  (min {min_occurrences} occurrences)")
            exp = defaultdict(Counter)
            for snippet, n in _query(conn, PASSAGES_SQL, {"min_occurrences": min_occurrences}):
                for a, ph in harvest_parentheticals_text(str(snippet), stopwords):
                    exp[a][ph] += int(n)
            write_tsv(exp, blocked, DATA / "passage_candidates.tsv", "passages")
    finally:
        conn.close()


# ============================================================================
# STEP 2 - did users ever actually search these acronyms?
# ============================================================================

SEARCH_TERMS_SQL = """
SELECT SEARCH_TERM, FIRST_SEEN_DATE, HOST
FROM PRODUCTION.PUBLISHED.ANALYTICS_SEARCH_TERM_FIRST_SEEN
"""


def step_evidence() -> None:
    acronyms = {}
    for name in ("passage_candidates.tsv", "title_candidates.tsv"):
        path = DATA / name
        if not path.exists():
            sys.exit(f"{path} missing - run `run.py fetch` first")
        for r in csv.DictReader(path.open(), delimiter="\t"):
            acronyms.setdefault(r["acronym"], r["expansion"])
    print(f"{len(acronyms)} acronyms to check")

    conn = _connect()
    try:
        cur = conn.cursor()
        t0 = time.time()
        cur.execute(SEARCH_TERMS_SQL)
        raw = cur.fetchall()
    finally:
        conn.close()
    print(f"{len(raw):,} search terms in {time.time() - t0:.1f}s")

    terms, exact, tokmap = [], defaultdict(list), defaultdict(list)
    for term, seen, host in raw:
        text = unquote(str(term or "")).lower().strip()
        if not text:
            continue
        tokens = set(re.findall(r"[a-z0-9']+", text))
        terms.append((text, seen, str(host), tokens))
        exact[text].append((seen, str(host)))
    for text, seen, host, tokens in terms:
        for tok in tokens:
            tokmap[tok].append((text, seen, host))

    out = {}
    for acronym, expansion in acronyms.items():
        ex = exact.get(acronym, [])
        inq = [t for t in tokmap.get(acronym, []) if t[0] != acronym]
        want = set(expansion.split())
        expm = [(t, s, h) for t, s, h, tk in terms if want and want <= tk]
        dates = [d for d, _ in ex] + [x[1] for x in inq] + [x[1] for x in expm]
        out[acronym] = {
            "exact": len(ex), "inq": len(inq), "expm": len(expm),
            "first": min(dates).isoformat() if dates else "",
            "cpr": any(h in CPR_HOSTS for _, h in ex),
        }

    path = DATA / "search_evidence.json"
    json.dump(out, path.open("w"), indent=0, sort_keys=True)
    hit = sum(1 for v in out.values() if v["exact"])
    any_ = sum(1 for v in out.values() if v["exact"] or v["inq"] or v["expm"])
    print(f"  -> {path.name}: {hit} typed exactly, {any_} with any evidence, of {len(out)}")



# ============================================================================
# JUDGING - shared by steps 3, 4 and 5
# ============================================================================
#
# One verdict per candidate, so a row cannot be Yes in the spreadsheet and Maybe in
# the CSV.

# Acronyms that are also ordinary words: a rule on one fires on queries that never
# meant the acronym. Curated - see everyday() for why the dictionary cannot do this.
AMBIGUOUS = {"of", "can", "cap", "nap", "bat", "api", "ara", "soc", "act", "law", "aid",
             "air", "end", "net", "use", "key", "gas", "map", "set", "top", "arc", "tax",
             "re", "un", "ef", "ad", "abs",
             # missed at first; CITES is the cautionary one - a real treaty acronym
             # that is also the ordinary verb "cites"
             "cites", "sea", "sec", "list", "cat", "ace", "ice", "needs", "snap", "pact",
             "car", "cod", "tea", "tar", "gap", "pop", "rap", "doc", "who", "its"}

# macOS only; missing means the dictionary pass is skipped, with a warning.
WORDS_FILE = Path("/usr/share/dict/words")

# web2 has no inflections ("cite" yes, "cites" no), hence the suffix stripping. Stems
# stay 3+ chars or "aws" reduces to "aw" and AWS is called an everyday word.
MIN_STEM = 3
SUFFIXES = ("s", "es", "ed", "ing")

DECISION_ORDER = {"Yes": 0, "Maybe": 1, "No": 2}


def load_english_words() -> set[str]:
    if not WORDS_FILE.exists():
        print(f"WARNING: {WORDS_FILE} not found - only the hand-maintained AMBIGUOUS set "
              "will be screened for everyday words", file=sys.stderr)
        return set()
    return {w.strip().lower() for w in WORDS_FILE.read_text().splitlines() if w.strip()}


def english_word(acronym: str, words: set[str]) -> str:
    """The dictionary form behind an acronym, or "" - "cites" -> "cite", "aws" -> ""."""
    if len(acronym) >= MIN_STEM and acronym in words:
        return acronym
    for suffix in SUFFIXES:
        stem = acronym[: -len(suffix)]
        if acronym.endswith(suffix) and len(stem) >= MIN_STEM:
            if stem in words:
                return stem
            if suffix in ("ed", "ing") and stem + "e" in words:
                return stem + "e"
    return ""


@dataclass(frozen=True)
class Context:
    """The data/ files, read once."""

    words: set[str]
    evidence: dict
    unterm: dict
    existing: set[str]       # acronyms already carrying a rule in the .sr files
    title_count: dict[str, int]
    candidates: list[tuple[dict, bool]]   # (row, found only in titles)


@dataclass(frozen=True)
class Verdict:
    """One candidate, judged. A reviewer reads `why`, so it must stay honest."""

    row: dict
    from_titles: bool
    group: str
    decision: str
    why: str
    everyday: str        # the ordinary word it collides with, or ""
    dictionary: str      # a dictionary hit worth a warning, or ""

    @property
    def acronym(self) -> str:
        """The acronym itself."""
        return self.row["acronym"]

    @property
    def count(self) -> int:
        """Times seen in passages, or in titles for a titles-only candidate."""
        return self.row["count"]


def _load_tsv(name: str, count_col: str) -> list[dict]:
    rows = list(csv.DictReader((DATA / name).open(), delimiter="\t"))
    for r in rows:
        r["count"] = int(r[count_col])
    return rows


def _load_json(name: str) -> dict:
    path = DATA / name
    return json.loads(path.read_text()) if path.exists() else {}


def load_context() -> Context:
    passages = _load_tsv("passage_candidates.tsv", "passages")
    titles = _load_tsv("title_candidates.tsv", "titles")
    in_passages = {r["acronym"] for r in passages}
    return Context(
        words=load_english_words(),
        evidence=_load_json("search_evidence.json"),
        unterm=_load_json("unterm.json"),
        existing={r["acronym"] for r in passages + titles if "already a rule" in r["note"]},
        title_count={r["acronym"]: r["count"] for r in titles},
        candidates=[(r, False) for r in passages]
                   + [(r, True) for r in titles if r["acronym"] not in in_passages],
    )


def group_of(ctx: Context, row: dict, from_titles: bool) -> str:
    if from_titles:
        return "4 - Only in titles"
    if len(row["acronym"]) == 2:
        return "3 - Two letters (skip)"
    if row["status"] == "review" or row["acronym"] in ctx.existing:
        return "2 - Clash or unclear"
    return "1 - Best picks"


def everyday(acronym: str) -> str:
    """
    The ordinary word this acronym is, or "".

    Only the curated list downgrades a suggestion. web2 is unabridged - it holds guan,
    kea, nid, ria - so letting it vote demoted real acronyms (ira, nepa, sids). It
    warns instead, which is how cites was caught.
    """
    return acronym if acronym in AMBIGUOUS else ""


def _unterm_is_ambiguous(ctx: Context, acronym: str) -> bool:
    return AMBIGUOUS_LABEL.get(ctx.unterm.get(acronym, {}).get("match", "")) == "Ambiguous"


def _decide(ctx: Context, row: dict, group: str, word: str, dictionary: str) -> tuple[str, str]:
    """(decision, why). A human reads `why`, so it claims only what was checked."""
    searched = ctx.evidence.get(row["acronym"], {})
    if group.startswith("3"):
        return "No", "two letters - too easily confused with country codes"

    if searched.get("exact"):
        if word:
            return "Maybe", f'users type it, but it is also the everyday word "{word}"'
        if group.startswith("2"):
            return "Maybe", "users type it, but see the warning column"
        # A differing UNTERM entry means another domain's meaning (cbd is cannabidiol
        # there), not that ours is wrong - but it is a second meaning, so: human look.
        if _unterm_is_ambiguous(ctx, row["acronym"]):
            return "Maybe", "users type it, but UNTERM lists another meaning"
        if dictionary:
            return "Yes", "users type this, but the dictionary lists it too - see the warning"
        return "Yes", "users type this, and it is not an everyday word"

    if searched.get("inq") and not word:
        return "Maybe", "only seen inside longer searches"
    if searched.get("expm"):
        return "Maybe", "only the long name was searched, not the acronym"
    if searched.get("inq"):
        return "Maybe", "weak - the acronym is also a normal word"
    return "No", "nobody has searched this in 3 years"


def judge(ctx: Context, row: dict, from_titles: bool) -> Verdict:
    acronym = row["acronym"]
    group = group_of(ctx, row, from_titles)
    word = everyday(acronym)
    dictionary = "" if word else english_word(acronym, ctx.words)
    decision, why = _decide(ctx, row, group, word, dictionary)
    return Verdict(row, from_titles, group, decision, why, word, dictionary)


def judge_all(ctx: Context) -> list[Verdict]:
    """Every candidate: Yes first, then by group, search evidence, frequency."""
    verdicts = [judge(ctx, row, ft) for row, ft in ctx.candidates]
    return sorted(verdicts, key=lambda v: (
        DECISION_ORDER[v.decision],
        v.group,
        -(1 if ctx.evidence.get(v.acronym, {}).get("exact") else 0),
        -v.count,
    ))


def load_and_judge() -> tuple[Context, list[Verdict]]:
    ctx = load_context()
    if not ctx.evidence:
        print("NOTE: search_evidence.json missing - run `run.py evidence`. "
              "Evidence columns will be empty.")
    return ctx, judge_all(ctx)


# ============================================================================
# STEP 3 - the review spreadsheet
# ============================================================================

class Column(NamedTuple):
    label: str
    kind: str    # picks the header colour
    width: int


COLUMNS = [
    Column("DECISION", "act", 12),
    Column("Acronym", "id", 11),
    Column("What it stands for", "id", 44),
    Column("Why we suggested that", "act", 30),
    Column("Group", "grp", 21),
    Column("User typed the acronym", "ev", 15),
    Column("Used in a longer search", "ev", 15),
    Column("User typed the long name", "ev", 15),
    Column("First searched", "ev", 13),
    Column("Times in documents", "doc", 13),
    Column("Times in titles", "doc", 11),
    Column("In UNTERM", "ext", 11),
    Column("UNTERM says", "ext", 40),
    Column("Agrees with us", "ext", 14),
    Column("UNTERM link", "ext", 46),
    Column("Anything to watch out for", "warn", 42),
    Column("Rule to paste into documents.sr", "rule", 54),
]

# Yes/No cells that get a green or grey fill, and cells that are merely centred.
SHADED = ("User typed the acronym", "Used in a longer search", "User typed the long name")
CENTRED = ("First searched", "Times in documents", "Times in titles", "In UNTERM",
           "Agrees with us")

HEADER_ROW, DECISION_COL = 3, 1
COLOURS = {"grp": "595959", "id": "1F3864", "act": "2E75B6", "ev": "548235",
           "doc": "7F6000", "ext": "833C00", "warn": "7B7B7B", "rule": "7B7B7B"}

LEGEND = (
    "DECISION is a pre-filled SUGGESTION - change it with the dropdown. Only 'Group 1 - Best picks' "
    "can be suggested Yes; anything clashing with a country code or two letters long is capped at "
    "Maybe however often it is searched.        GROUPS: 1 Best picks = in document text, no known "
    "clash. 2 Clash or unclear = country-code collision, already a rule, or several meanings. "
    "3 Two letters = recommend skipping all. 4 Only in titles = in titles, not body text.        "
    "DID USERS SEARCH IT? - 83,628 real searches on CPR sites since 7 Sept 2023. 'User typed the "
    "acronym' is the one to trust; 'long name' is weakest, inflated by court case names. 'No' means "
    "no evidence, not never.        UNTERM = the UN terminology database. 'Ambiguous' means the letters "
    "mean something else there too (cbd is cannabidiol at the UN) - not that our expansion is wrong."
)


def _column_index(label: str) -> int:
    """1-based, as openpyxl counts."""
    return next(i for i, c in enumerate(COLUMNS, 1) if c.label == label)


def warning_for(v: Verdict) -> str:
    """The 'watch out for' cell: our note, prefixed by any word clash."""
    if v.everyday:
        return ("Also an everyday English word. " + v.row["note"]).strip()
    if v.dictionary:
        return (f'The dictionary also has "{v.dictionary}" - check it is not a word '
                "people type. " + v.row["note"]).strip()
    return v.row["note"]


def row_values(ctx: Context, v: Verdict) -> list:
    """One row, in COLUMNS order."""
    searched = ctx.evidence.get(v.acronym, {})
    un = ctx.unterm.get(v.acronym, {})

    def yes_no(key: str) -> str:
        return "Yes" if searched.get(key) else "No"

    return [
        v.decision, v.acronym, v.row["expansion"], v.why, v.group,
        yes_no("exact"), yes_no("inq"), yes_no("expm"), searched.get("first", ""),
        "" if v.from_titles else v.count, ctx.title_count.get(v.acronym, ""),
        un.get("found", ""), un.get("expansion", ""),
        AMBIGUOUS_LABEL.get(un.get("match", ""), un.get("match", "")), un.get("link", ""),
        warning_for(v), v.row["rule_line"],
    ]


def step_workbook() -> None:
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    ctx, verdicts = load_and_judge()
    counts = Counter(v.decision for v in verdicts)
    to_review = [v for v in verdicts if v.decision != "No"]
    suggested_no = [v for v in verdicts if v.decision == "No"]

    wb = Workbook()
    if wb.active is not None:
        wb.remove(wb.active)   # drop the default empty sheet
    thin = Side(style="thin", color="FFFFFF")
    yes_fill = PatternFill("solid", fgColor="C6EFCE")
    no_fill = PatternFill("solid", fgColor="F2F2F2")
    shaded = [_column_index(label) for label in SHADED]
    centred = [_column_index(label) for label in CENTRED]

    def add_sheet(title, sheet_verdicts, blurb):
        ws = wb.create_sheet(title)
        ws["A1"] = blurb
        ws["A1"].font = Font(bold=True, size=11, color="1F3864")
        ws["A2"] = LEGEND
        ws["A2"].font = Font(italic=True, size=9, color="666666")

        for c, column in enumerate(COLUMNS, 1):
            cell = ws.cell(row=HEADER_ROW, column=c, value=column.label)
            cell.fill = PatternFill("solid", fgColor=COLOURS[column.kind])
            cell.font = Font(bold=True, color="FFFFFF", size=10)
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            cell.border = Border(left=thin, right=thin)
            ws.column_dimensions[get_column_letter(c)].width = column.width
        ws.row_dimensions[HEADER_ROW].height = 42

        for i, v in enumerate(sheet_verdicts):
            for c, value in enumerate(row_values(ctx, v), 1):
                ws.cell(row=HEADER_ROW + 1 + i, column=c, value=value)

        first, last = HEADER_ROW + 1, HEADER_ROW + len(sheet_verdicts)
        for r in range(first, last + 1):
            for c in shaded:
                cell = ws.cell(row=r, column=c)
                cell.fill = yes_fill if cell.value == "Yes" else no_fill
                cell.alignment = Alignment(horizontal="center")
            for c in centred:
                ws.cell(row=r, column=c).alignment = Alignment(horizontal="center")
            decision = ws.cell(row=r, column=DECISION_COL)
            decision.alignment = Alignment(horizontal="center")
            decision.font = Font(bold=True, size=11)

        col = get_column_letter(DECISION_COL)
        rng = f"{col}{first}:{col}{last}"
        dv = DataValidation(type="list", formula1='"Yes,Maybe,No"', allow_blank=True, showDropDown=False)
        dv.promptTitle = "Decision"
        dv.prompt = "Yes = add this rule.  Maybe = needs thought.  No = skip."
        ws.add_data_validation(dv)
        dv.add(rng)
        for value, colour in (("Yes", "A9D08E"), ("Maybe", "FFE699"), ("No", "D9D9D9")):
            ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{value}"'],
                                                          fill=PatternFill("solid", fgColor=colour)))
        ws.freeze_panes = f"D{first}"
        ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(COLUMNS))}{last}"

    add_sheet("Review these", to_review,
              f"{len(to_review)} acronyms worth a decision: {counts['Yes']} suggested Yes, "
              f"{counts['Maybe']} Maybe. Sorted Yes first. Work top-down and stop when it thins out.")
    add_sheet("Suggested no", suggested_no,
              f"{len(suggested_no)} acronyms suggested No: no search evidence in three years, or only "
              "two letters long. Not worthless - they are genuinely in our documents, just unevidenced. "
              "Skim if you want; the decision dropdown works here too.")

    out = DATA / "acronym_candidates.xlsx"
    wb.save(out)
    print(f"  -> {out.name}: 'Review these' {len(to_review)} rows "
          f"({counts['Yes']} Yes, {counts['Maybe']} Maybe), 'Suggested no' {len(suggested_no)} rows"
          + ("" if ctx.unterm else "   [no unterm.json yet - those columns are blank]"))


# ============================================================================
# STEP 4 (optional) - the same table as a CSV, for Google Sheets
# ============================================================================

# Leading =, +, - or @ makes Sheets parse a cell as a formula. Nothing trips it today,
# but the rule column is meant to be copied out verbatim.
FORMULA_LEAD = ("=", "+", "-", "@")


def _sheets_safe(value):
    return f"'{value}" if isinstance(value, str) and value.startswith(FORMULA_LEAD) else value


def step_sheets(review_only: bool = False) -> None:
    """
    The review table as a CSV, for Google Sheets.

    Both workbook sheets in one file; --review-only keeps just 'Review these'. A No
    means no search evidence since Sept 2023, not a wrong acronym, so nothing is lost
    for good - rerun without the flag. The dropdown and colours cannot survive a CSV;
    the command prints the clicks that restore them.
    """
    ctx, verdicts = load_and_judge()
    counts = Counter(v.decision for v in verdicts)
    if review_only:
        verdicts = [v for v in verdicts if v.decision != "No"]

    out = DATA / "acronym_candidates_sheets.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([c.label for c in COLUMNS])
        for v in verdicts:
            writer.writerow([_sheets_safe(value) for value in row_values(ctx, v)])

    dropped = f", {counts['No']} suggested No left out" if review_only else f", {counts['No']} No"
    print(f"  -> {out.name}: {len(verdicts)} rows, {len(COLUMNS)} columns "
          f"({counts['Yes']} Yes, {counts['Maybe']} Maybe{dropped})")
    print("     File > Import > Upload, and choose 'Replace spreadsheet'.")
    print("     Then, to get the workbook's behaviour back:")
    print("       1. View > Freeze > 1 row, and Data > Create a filter.")
    print("       2. Select column A, Data > Data validation, Dropdown: Yes, Maybe, No.")
    if not review_only:
        print("       3. Filter column A to 'No' and collapse it - that is the 'Suggested no' sheet.")


# ============================================================================
# STEP 5 (optional) - a CSV shaped for importing into Notion
# ============================================================================
#
# Deliberately does not reuse judge(): it answers "what should a reviewer check?", so it
# leads with a risk and is worded for a Notion board with no legend. If the two ever
# must agree, collapse them rather than hand-syncing.

NOTION_HEADER = ["Acronym", "Means", "Decision", "What to check", "Evidence", "Risk",
                 "Times in documents", "Other meaning", "Rule to paste", "UNTERM link"]


def _other_meaning(ctx: Context, acronym: str) -> str:
    un = ctx.unterm.get(acronym, {})
    return un.get("expansion", "") if _unterm_is_ambiguous(ctx, acronym) else ""


def _evidence_label(ctx: Context, acronym: str) -> str:
    searched = ctx.evidence.get(acronym, {})
    if searched.get("exact"):
        return "Users type it"
    if searched.get("inq"):
        return "Only in longer searches"
    if searched.get("expm"):
        return "Only the long name"
    return "Never searched"


def _risk_label(ctx: Context, row: dict, from_titles: bool) -> str:
    acronym = row["acronym"]
    if from_titles:
        return "Only in titles"
    if len(acronym) == 2:
        return "Two letters"
    if acronym in ctx.existing:
        return "Already a rule"
    if "ISO" in row["note"] or "geo synonym" in row["note"]:
        return "Country code clash"
    if row["status"] == "review":
        return "Several meanings"
    if _other_meaning(ctx, acronym):
        return "Other meaning at the UN"
    if acronym in AMBIGUOUS:
        return "Everyday English word"
    return "Clear"


def assess(ctx: Context, row: dict, from_titles: bool) -> tuple[str, str, str, str]:
    """(decision, evidence, risk, what_to_check) for one Notion row."""
    acronym = row["acronym"]
    ev = _evidence_label(ctx, acronym)
    risk = _risk_label(ctx, row, from_titles)
    other = _other_meaning(ctx, acronym)

    # Risk first: a clash matters however often the acronym is searched.
    blocking = {
        "Two letters": ("No", "Two letters is too short - it will collide with country codes. Recommend skipping."),
        "Already a rule": ("No", "Already in documents.sr. Nothing to do."),
        "Country code clash": ("Maybe", f"Clashes with a country code ({row['note'][:60]}). Only add if geography search will not suffer."),
        "Several meanings": ("Maybe", f"Our own documents use it more than one way ({row['note'][:70]}). Pick the right expansion or skip."),
        "Everyday English word": ("Maybe", "Also a normal English word, so it will fire on ordinary queries. Probably skip."),
    }
    if risk in blocking:
        decision, check = blocking[risk]
        return decision, ev, risk, check

    if ev == "Users type it":
        if other:
            return "Maybe", ev, risk, f'Users do type this. But UNTERM also has it as "{other[:45]}" - would our users ever mean that? If not, say Yes.'
        return "Yes", ev, risk, "Users type it, it is in our documents, and nothing clashes. Check the expansion reads right, then add."
    if ev == "Only in longer searches":
        return "Maybe", ev, risk, "Nobody has typed this on its own, only inside longer searches. Worth adding if you expect people to."
    if ev == "Only the long name":
        return "Maybe", ev, risk, "People search the full name, not the acronym. This rule only helps someone who types the acronym."
    return "No", ev, risk, "Nobody has searched this in three years. In our documents, but no sign anyone wants it."


def step_notion() -> None:
    """
    A stripped-down review list for Notion.

    Ten columns answering one question per row: should this become a search rule? The
    one that matters is "What to check" - a plain-English prompt, so nobody has to
    interpret the evidence columns themselves.

    Notion makes the first column the page Title, hence Acronym first. After import set
    Decision, Evidence, Risk -> Select; Times in documents -> Number; UNTERM link ->
    URL, then group a board view by Decision.
    """
    ctx = load_context()
    assessed = [(row, ft, assess(ctx, row, ft)) for row, ft in ctx.candidates]
    assessed.sort(key=lambda item: (DECISION_ORDER[item[2][0]], -item[0]["count"]))

    out = DATA / "acronym_candidates_notion.csv"
    counts: Counter = Counter()
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(NOTION_HEADER)
        for row, from_titles, (decision, ev, risk, check) in assessed:
            acronym = row["acronym"]
            counts[decision] += 1
            writer.writerow([acronym, row["expansion"], decision, check, ev, risk,
                             "" if from_titles else row["count"], _other_meaning(ctx, acronym),
                             row["rule_line"], ctx.unterm.get(acronym, {}).get("link", "")])
    print(f"  -> {out.name}: {len(assessed)} rows, {len(NOTION_HEADER)} columns "
          f"({counts['Yes']} Yes, {counts['Maybe']} Maybe, {counts['No']} No)")


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", default="all",
                    choices=["all", "fetch", "evidence", "workbook", "sheets", "notion"],
                    help="which step to run (default: all)")
    ap.add_argument("--titles-only", action="store_true", help="fetch: titles only, skip passages")
    ap.add_argument("--passages-only", action="store_true", help="fetch: passages only, skip titles")
    ap.add_argument("--review-only", action="store_true",
                    help="sheets: leave out the rows suggested No")
    ap.add_argument("--min-occurrences", type=int, default=MIN_OCCURRENCES,
                    help=f"fetch: passage threshold (default {MIN_OCCURRENCES})")
    args = ap.parse_args()

    if args.step in ("all", "fetch"):
        step_fetch(titles=not args.passages_only,
                   passages=not args.titles_only,
                   min_occurrences=args.min_occurrences)
    if args.step in ("all", "evidence"):
        step_evidence()
    if args.step in ("all", "workbook"):
        step_workbook()
    if args.step in ("all", "sheets"):
        step_sheets(review_only=args.review_only)
    if args.step in ("all", "notion"):
        step_notion()


if __name__ == "__main__":
    main()
