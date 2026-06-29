"""
Generate an HTML "vibe check" page comparing document-topic predictors.

For domain experts to sense-check the document-topic relevance predictors side
by side.

Compares two predictors on the eval set:
  - "mention-density": raw share of a document's passages that mention the topic.
  - "tfidf-density-cf": the same density weighted by the topic's inverse
    *collection* frequency (rarer topics weighted up).

Both predictors' {0, 1, 2} scores are shown labelled side by side against the
ground-truth score, in three views: pairwise, grouped by document, and grouped
by topic. Run with `uv run python vibe_check.py` (or `just vibe-check`).
"""

from pathlib import Path
from typing import cast
from urllib.parse import quote_plus

from evaluate_predictors import PREDICTORS
from jinja2 import Environment, select_autoescape
from load_dataset import load_enriched_dataset_from_jsonl
from rich.console import Console
from src.models import EvalExample
from src.predictors import ThresholdPredictor

console = Console()

DENSITY_KEY = "mention-density"
CF_KEY = "tfidf-density-cf"

SCORE_LABELS = {0: "not relevant", 1: "somewhat", 2: "relevant"}

# Resolve the two predictors once, keeping their tuned thresholds in sync with
# evaluate_predictors.py. They are ThresholdPredictor subclasses, so they expose
# the `.feature()` accessor; the loop below guards that at runtime.
DENSITY_PREDICTOR = cast(ThresholdPredictor, PREDICTORS[DENSITY_KEY])
CF_PREDICTOR = cast(ThresholdPredictor, PREDICTORS[CF_KEY])
for _key, _predictor in ((DENSITY_KEY, DENSITY_PREDICTOR), (CF_KEY, CF_PREDICTOR)):
    if not isinstance(_predictor, ThresholdPredictor):
        raise TypeError(f"{_key} must be a ThresholdPredictor to expose `.feature()`")


def _build_row(ex: EvalExample) -> dict:
    """Project one EvalExample into the flat dict shape the template consumes."""
    density_predictor = DENSITY_PREDICTOR
    cf_predictor = CF_PREDICTOR

    mentions = ex.input.mentions
    corpus = ex.input.topic_corpus

    score_density = int(density_predictor.predict(ex.input))
    score_cf = int(cf_predictor.predict(ex.input))
    truth = int(ex.score)

    # The dataset's stored source_url is often a placeholder, so link to a title
    # search in the CPR app instead — that reliably lands on the document.
    title = ex.input.document.title or ""
    search_url = "https://app.climatepolicyradar.org/_search?q=" + quote_plus(
        title, safe="()"
    )

    return {
        "topic_id": ex.input.topic.id,
        "topic_value": ex.input.topic.value,
        "topic_description": ex.input.topic.description or "",
        "doc_id": ex.input.document.original_document_id,
        "doc_title": title or "(untitled)",
        "doc_description": ex.input.document.description or "",
        "source_url": search_url,
        "count": mentions.count,
        "total_passages": mentions.total_passages,
        "density": mentions.density,
        "density_feature": density_predictor.feature(ex.input),
        "cf_feature": cf_predictor.feature(ex.input),
        "idf_cf": corpus.idf_cf() if corpus is not None else None,
        "score_density": score_density,
        "score_cf": score_cf,
        "truth": truth,
        "models_disagree": score_density != score_cf,
        "density_matches_truth": score_density == truth,
        "cf_matches_truth": score_cf == truth,
    }


def _group_by_document(rows: list[dict]) -> list[dict]:
    """Group rows by document; one entry per document with its topic rows."""
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(
            r["doc_id"],
            {
                "doc_id": r["doc_id"],
                "doc_title": r["doc_title"],
                "doc_description": r["doc_description"],
                "source_url": r["source_url"],
                "rows": [],
            },
        )
        g["rows"].append(r)
    out = list(groups.values())
    for g in out:
        g["n_disagree"] = sum(1 for r in g["rows"] if r["models_disagree"])
        # Default order: ground truth descending (the in-page JS can re-sort by A/B/GT).
        g["rows"].sort(
            key=lambda r: (r["truth"], r["score_cf"], r["density_feature"]),
            reverse=True,
        )
    # Documents with the most disagreement first.
    out.sort(key=lambda g: (-g["n_disagree"], g["doc_title"].lower()))
    return out


def _group_by_topic(rows: list[dict]) -> list[dict]:
    """Group rows by topic; documents sorted by density feature (highest first)."""
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(
            r["topic_id"],
            {
                "topic_id": r["topic_id"],
                "topic_value": r["topic_value"],
                "topic_description": r["topic_description"],
                "rows": [],
            },
        )
        g["rows"].append(r)
    out = list(groups.values())
    for g in out:
        g["n_disagree"] = sum(1 for r in g["rows"] if r["models_disagree"])
        # Default order: ground truth descending (the in-page JS can re-sort by A/B/GT).
        g["rows"].sort(
            key=lambda r: (r["truth"], r["score_cf"], r["density_feature"]),
            reverse=True,
        )
    out.sort(key=lambda g: g["topic_value"].lower())
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Predictor vibe check — density vs tfidf-density-cf</title>
<style>
  :root {
    --green: #1f7a3a; --green-bg: #e8f5ec;
    --amber: #92600a; --amber-bg: #fff3d6;
    --grey: #6b7280; --grey-bg: #f1f3f5;
    --flag: #b3261e; --flag-bg: #fde8e6;
    --muted: #6b7280; --border: #e5e7eb; --bg: #fafafa; --card: #ffffff;
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 0 2rem 4rem; background: var(--bg); color: #111; line-height: 1.45; }
  h1 { margin: 1.5rem 0 0.25rem; font-size: 1.5rem; }
  h2 { margin: 2.5rem 0 0.5rem; font-size: 1.2rem; border-bottom: 1px solid var(--border);
       padding-bottom: 0.3rem; scroll-margin-top: 4rem; }
  a { color: #1d4ed8; }
  nav { position: sticky; top: 0; background: var(--bg); padding: 0.75rem 0; margin-bottom: 0.5rem;
        border-bottom: 1px solid var(--border); z-index: 10; font-size: 0.9rem; }
  nav a { margin-right: 1.25rem; font-weight: 600; text-decoration: none; }
  .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1rem; }
  .summary { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
             padding: 1rem 1.25rem; margin-bottom: 0.5rem; }
  .summary .stat { display: inline-block; margin-right: 2rem; }
  .summary .stat b { font-size: 1.4rem; display: block; }
  .summary .stat span { color: var(--muted); font-size: 0.85rem; }
  .caveat { background: #fff8e1; border-left: 3px solid #d97706; padding: 0.6rem 0.9rem;
            margin: 0.75rem 0 1rem; font-size: 0.88rem; color: #7c4a00; border-radius: 0 4px 4px 0; }
  .legend { font-size: 0.85rem; color: var(--muted); margin: 0.5rem 0 1rem; }
  .chip { font-family: var(--mono); font-size: 0.78rem; font-weight: 700; padding: 0.1rem 0.45rem;
          border-radius: 4px; white-space: nowrap; }
  .chip.correct { background: var(--green-bg); color: var(--green); }
  .chip.incorrect { background: var(--flag-bg); color: var(--flag); }
  .chip.gt { background: var(--grey-bg); color: #111; border: 1px solid var(--border); }
  .flag { background: var(--flag-bg); color: var(--flag); font-size: 0.7rem; font-weight: 700;
          padding: 0.1rem 0.4rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.04em; }
  table.grid { border-collapse: collapse; width: 100%; background: var(--card);
               border: 1px solid var(--border); border-radius: 6px; font-size: 0.88rem; }
  table.grid th, table.grid td { padding: 0.45rem 0.6rem; text-align: left;
                                  border-bottom: 1px solid var(--border); vertical-align: top; }
  table.grid th { color: var(--muted); font-weight: 600; font-size: 0.78rem;
                  text-transform: uppercase; letter-spacing: 0.04em; background: var(--bg); }
  table.grid tr:last-child td { border-bottom: none; }
  tr.disagree td { background: var(--flag-bg); }
  tr.disagree td:first-child { box-shadow: inset 3px 0 0 var(--flag); }
  .num { font-family: var(--mono); text-align: right; white-space: nowrap; }
  .id { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); }
  .desc { color: #374151; font-size: 0.85rem; margin-top: 0.15rem; }
  th.score-col, td.score-col { text-align: center; }
  td.score-col.num { text-align: right; }
  th.grp { text-align: center; }
  th.gstart, td.gstart { border-left: 1px solid var(--border); }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: #111; }
  th.sortable.sorted-desc::after { content: " ▼"; font-size: 0.8em; }
  th.sortable.sorted-asc::after { content: " ▲"; font-size: 0.8em; }
  .mark { font-weight: 700; }
  .mark.correct { color: var(--green); }
  .mark.incorrect { color: var(--flag); }
  details.group { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
                  margin: 0.5rem 0; }
  details.group > summary { padding: 0.7rem 1rem; cursor: pointer; list-style: none;
                            display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
  details.group > summary::-webkit-details-marker { display: none; }
  details.group > summary::before { content: "▸"; color: var(--muted); }
  details.group[open] > summary::before { content: "▾"; }
  details.group > summary .name { font-weight: 600; }
  details.group .group-body { padding: 0 1rem 1rem; }
</style>
</head>
<body>

<nav>
  <a href="#pairwise">Pairwise</a>
  <a href="#by-document">By document</a>
  <a href="#by-topic">By topic</a>
</nav>

<h1>Predictor vibe check</h1>
<div class="meta">
  Comparing <code>mention-density</code> vs <code>tfidf-density-cf</code> on the eval set
  &middot; dataset: <code>{{ dataset_path }}</code>
</div>

<div class="summary">
  <div class="stat"><b>{{ n_pairs }}</b><span>topic–document pairs</span></div>
  <div class="stat"><b>{{ n_docs }}</b><span>documents</span></div>
  <div class="stat"><b>{{ n_topics }}</b><span>topics</span></div>
  <div class="stat"><b>{{ n_disagree }}</b><span>model disagreements</span></div>
</div>

<div class="caveat">
  <b>Note on the CF weighting:</b> the inverse-collection-frequency weight is a per-topic
  constant, so <b>within a single topic</b> the two predictors rank documents identically — only
  the absolute score can differ (one shared threshold). The CF weighting only re-orders things
  <b>across</b> topics, so the “by document” view is where the two approaches diverge most.
</div>

<div class="legend">
  The <b>mention-density</b> and <b>tfidf-density-cf</b> predictors are compared against
  <b>GT</b> (ground truth). Each predictor shows <b>score</b> (continuous feature),
  <b>pred</b> (0/1/2 class) and <b>✓</b> (matches GT). Class values: 0 not relevant,
  1 somewhat, 2 relevant.
  &middot; <span class="chip correct">2</span> / <span class="mark correct">✓</span> matches GT,
  <span class="chip incorrect">2</span> / <span class="mark incorrect">✗</span> differs from GT.
  &middot; Rows where the two predictors disagree are highlighted red.
  &middot; In the grouped views, click a predictor or <b>GT</b> column header to sort
  (default GT, descending).
</div>

{% macro pred_chip(score, correct) -%}
  <span class="chip {{ 'correct' if correct else 'incorrect' }}" title="{{ 'matches' if correct else 'differs from' }} ground truth">{{ score }}</span>
{%- endmacro %}

{% macro gt_chip(score) -%}
  <span class="chip gt">{{ score }}</span>
{%- endmacro %}

{% macro correct_mark(correct) -%}
  <span class="mark {{ 'correct' if correct else 'incorrect' }}" title="{{ 'matches' if correct else 'differs from' }} ground truth">{{ '✓' if correct else '✗' }}</span>
{%- endmacro %}

{# Per-model block: score (continuous feature), pred (class chip), ✓ (matches GT). #}
{% macro score_cells(r) -%}
  <td class="num score-col gstart">{{ "%.4f"|format(r.density_feature) }}</td>
  <td class="score-col">{{ pred_chip(r.score_density, r.density_matches_truth) }}</td>
  <td class="score-col">{{ correct_mark(r.density_matches_truth) }}</td>
  <td class="num score-col gstart">{{ "%.4f"|format(r.cf_feature) }}</td>
  <td class="score-col">{{ pred_chip(r.score_cf, r.cf_matches_truth) }}</td>
  <td class="score-col">{{ correct_mark(r.cf_matches_truth) }}</td>
  <td class="score-col gstart">{{ gt_chip(r.truth) }}</td>
{%- endmacro %}

{# Two-row grouped header. With sortable=true the A/B/GT cells re-sort the table
   (by A.score / B.score / GT columns 2 / 5 / 8 — the fixed layout of the grouped
   views); GT is the default-sorted column. #}
{% macro score_group_headers(sortable=false) -%}
  <th colspan="3" class="grp gstart{{ ' sortable' if sortable }}"{% if sortable %} data-sort-col="2"{% endif %} title="raw passage density">mention-density</th>
  <th colspan="3" class="grp gstart{{ ' sortable' if sortable }}"{% if sortable %} data-sort-col="5"{% endif %} title="density weighted by inverse collection frequency">tfidf-density-cf</th>
  <th rowspan="2" class="score-col gstart{{ ' sortable sorted-desc' if sortable }}"{% if sortable %} data-sort-col="8" data-sort="desc"{% endif %} title="ground truth">GT</th>
{%- endmacro %}

{% macro score_sub_headers() -%}
  <th class="score-col gstart">score</th><th class="score-col">pred</th><th class="score-col">✓</th>
  <th class="score-col gstart">score</th><th class="score-col">pred</th><th class="score-col">✓</th>
{%- endmacro %}

<h2 id="pairwise">Pairwise <span style="color:var(--muted);font-weight:normal;font-size:0.9rem;">({{ n_pairs }} pairs, disagreements first)</span></h2>
<table class="grid">
  <thead>
    <tr>
      <th rowspan="2">Topic</th><th rowspan="2">Document</th><th rowspan="2" class="num">mentions</th>
      {{ score_group_headers() }}
    </tr>
    <tr>{{ score_sub_headers() }}</tr>
  </thead>
  <tbody>
    {% for r in pairwise %}
      <tr class="{{ 'disagree' if r.models_disagree else '' }}">
        <td>{{ r.topic_value }}<div class="id">{{ r.topic_id }}</div></td>
        <td><a href="{{ r.source_url }}" target="_blank" rel="noopener">{{ r.doc_title }}</a>
            <div class="id">{{ r.doc_id }}</div></td>
        <td class="num">{{ r.count }}/{{ r.total_passages }}</td>
        {{ score_cells(r) }}
      </tr>
    {% endfor %}
  </tbody>
</table>

<h2 id="by-document">Grouped by document <span style="color:var(--muted);font-weight:normal;font-size:0.9rem;">({{ n_docs }} documents, most disagreement first)</span></h2>
{% for g in by_document %}
  <details class="group"{% if g.n_disagree %} open{% endif %}>
    <summary>
      <span class="name"><a href="{{ g.source_url }}" target="_blank" rel="noopener">{{ g.doc_title }}</a></span>
      <span class="id">{{ g.doc_id }}</span>
      {% if g.n_disagree %}<span class="flag">{{ g.n_disagree }} disagree</span>{% endif %}
    </summary>
    <div class="group-body">
      {% if g.doc_description %}<div class="desc">{{ g.doc_description }}</div>{% endif %}
      <table class="grid" style="margin-top:0.6rem;">
        <thead>
          <tr><th rowspan="2">Topic</th><th rowspan="2" class="num">mentions</th>{{ score_group_headers(true) }}</tr>
          <tr>{{ score_sub_headers() }}</tr>
        </thead>
        <tbody>
          {% for r in g.rows %}
            <tr class="{{ 'disagree' if r.models_disagree else '' }}">
              <td>{{ r.topic_value }}<div class="id">{{ r.topic_id }}</div></td>
              <td class="num">{{ r.count }}/{{ r.total_passages }}</td>
              {{ score_cells(r) }}
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </details>
{% endfor %}

<h2 id="by-topic">Grouped by topic <span style="color:var(--muted);font-weight:normal;font-size:0.9rem;">({{ n_topics }} topics)</span></h2>
{% for g in by_topic %}
  <details class="group">
    <summary>
      <span class="name">{{ g.topic_value }}</span>
      <span class="id">{{ g.topic_id }}</span>
      {% if g.n_disagree %}<span class="flag">{{ g.n_disagree }} disagree</span>{% endif %}
    </summary>
    <div class="group-body">
      {% if g.topic_description %}<div class="desc">{{ g.topic_description }}</div>{% endif %}
      <table class="grid" style="margin-top:0.6rem;">
        <thead>
          <tr><th rowspan="2">Document</th><th rowspan="2" class="num">mentions</th>{{ score_group_headers(true) }}</tr>
          <tr>{{ score_sub_headers() }}</tr>
        </thead>
        <tbody>
          {% for r in g.rows %}
            <tr class="{{ 'disagree' if r.models_disagree else '' }}">
              <td><a href="{{ r.source_url }}" target="_blank" rel="noopener">{{ r.doc_title }}</a>
                  <div class="id">{{ r.doc_id }}</div></td>
              <td class="num">{{ r.count }}/{{ r.total_passages }}</td>
              {{ score_cells(r) }}
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </details>
{% endfor %}

<script>
// Click an A / B / GT header in a grouped table to sort its rows by that column.
// First click on a column sorts descending; clicking again toggles ascending.
// Disagreement-row highlighting is preserved (it rides on the row, not the order).
(function () {
  document.querySelectorAll("th.sortable").forEach(function (th) {
    th.addEventListener("click", function () {
      var table = th.closest("table");
      var tbody = table.tBodies[0];
      var col = parseInt(th.getAttribute("data-sort-col"), 10);
      var next = th.getAttribute("data-sort") === "desc" ? "asc" : "desc";
      table.querySelectorAll("th.sortable").forEach(function (other) {
        other.removeAttribute("data-sort");
        other.classList.remove("sorted-asc", "sorted-desc");
      });
      th.setAttribute("data-sort", next);
      th.classList.add(next === "asc" ? "sorted-asc" : "sorted-desc");
      var rows = Array.prototype.slice.call(tbody.rows);
      rows.sort(function (a, b) {
        var va = parseFloat(a.cells[col].textContent) || 0;
        var vb = parseFloat(b.cells[col].textContent) || 0;
        return next === "asc" ? va - vb : vb - va;
      });
      rows.forEach(function (row) { tbody.appendChild(row); });
    });
  });
})();
</script>

</body>
</html>
"""


def render_vibe_check_html(rows: list[dict], dataset_path: str) -> str:
    """Render the rows into the self-contained HTML page."""
    pairwise = sorted(
        rows,
        key=lambda r: (
            not r["models_disagree"],
            r["topic_value"],
            r["doc_title"].lower(),
        ),
    )
    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    template = env.from_string(_TEMPLATE)
    return template.render(
        dataset_path=dataset_path,
        n_pairs=len(rows),
        n_docs=len({r["doc_id"] for r in rows}),
        n_topics=len({r["topic_id"] for r in rows}),
        n_disagree=sum(1 for r in rows if r["models_disagree"]),
        pairwise=pairwise,
        by_document=_group_by_document(rows),
        by_topic=_group_by_topic(rows),
    )


def main() -> None:
    input_path = Path(__file__).parent / Path("data/dataset.jsonl")
    output_path = Path(__file__).parent / Path("vibe_check.html")

    ds = load_enriched_dataset_from_jsonl(str(input_path))
    rows = [_build_row(ex) for ex in ds]

    n_docs = len({r["doc_id"] for r in rows})
    n_topics = len({r["topic_id"] for r in rows})
    n_disagree = sum(1 for r in rows if r["models_disagree"])
    console.log(
        f"📋 Loaded [bold]{len(rows)}[/bold] pairs "
        f"over {n_docs} documents and {n_topics} topics; "
        f"[bold]{n_disagree}[/bold] model disagreements"
    )

    output_path.write_text(render_vibe_check_html(rows, dataset_path=str(input_path)))
    console.log(f"💾 Wrote vibe check to [bold]{output_path}[/bold]")


if __name__ == "__main__":
    main()
