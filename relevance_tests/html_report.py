"""HTML report rendering for relevance test runs, intended for sharing with domain experts."""

from typing import Any

from jinja2 import Environment, select_autoescape

SCORE_FEATURES = [
    "title_score",
    "description_score",
    "passages_score",
    "geographies_score",
    "title_synonyms_score",
    "identifiers_score",
]


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Relevance test report — {{ engine_name }}</title>
<style>
  :root {
    --pass: #1f7a3a;
    --pass-bg: #e8f5ec;
    --fail: #b3261e;
    --fail-bg: #fde8e6;
    --muted: #6b7280;
    --border: #e5e7eb;
    --bg: #fafafa;
    --card: #ffffff;
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 2rem; background: var(--bg); color: #111; line-height: 1.45; }
  h1 { margin: 0 0 0.25rem 0; font-size: 1.5rem; }
  h2 { margin: 2rem 0 0.5rem 0; font-size: 1.15rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }
  .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .meta code { font-family: var(--mono); font-size: 0.85rem; }
  table { border-collapse: collapse; }
  .summary { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
             padding: 1rem; margin-bottom: 1.5rem; }
  .summary table { width: 100%; }
  .summary th, .summary td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid var(--border); }
  .summary th { font-weight: 600; color: var(--muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .summary tr:last-child td { border-bottom: none; }
  .summary .total td { font-weight: 600; }
  details.test { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
                 margin: 0.5rem 0; padding: 0; }
  details.test[open] { box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
  details.test > summary { padding: 0.75rem 1rem; cursor: pointer; display: flex; align-items: center;
                           gap: 0.75rem; list-style: none; }
  details.test > summary::-webkit-details-marker { display: none; }
  details.test > summary::before { content: "▸"; color: var(--muted); transition: transform 0.15s; }
  details.test[open] > summary::before { transform: rotate(90deg); }
  .badge { font-size: 0.75rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 4px;
           text-transform: uppercase; letter-spacing: 0.04em; }
  .badge.pass { background: var(--pass-bg); color: var(--pass); }
  .badge.fail { background: var(--fail-bg); color: var(--fail); }
  .test-body { padding: 0 1rem 1rem 1rem; }
  .test-meta { color: var(--muted); font-size: 0.9rem; margin: 0.25rem 0 0.75rem 0; }
  .query { font-family: var(--mono); background: #f3f4f6; padding: 0.15rem 0.4rem; border-radius: 3px; }
  .diagnosis { background: var(--fail-bg); border-left: 3px solid var(--fail); padding: 0.6rem 0.8rem;
               margin: 0.5rem 0 1rem 0; font-family: var(--mono); font-size: 0.85rem;
               white-space: pre-wrap; }
  .note { background: #fff8e1; border-left: 3px solid #d97706; padding: 0.5rem 0.8rem;
          margin: 0.5rem 0; font-size: 0.85rem; color: #7c4a00; }
  .results-heading { font-size: 0.8rem; font-weight: 600; color: var(--muted);
                     text-transform: uppercase; letter-spacing: 0.06em;
                     margin: 1rem 0 0.25rem 0; padding-bottom: 0.25rem;
                     border-bottom: 1px solid var(--border); }
  .result { border-top: 1px solid var(--border); padding: 0.75rem 0;
            display: grid; grid-template-columns: 1fr 16rem; gap: 1.5rem; align-items: start; }
  .result:last-child { padding-bottom: 0; }
  .result-main { min-width: 0; }
  .result-header { display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap; }
  .result-header .rank { font-weight: 600; color: var(--muted); }
  .result-header .title { font-weight: 600; }
  .result-header .id { font-family: var(--mono); font-size: 0.8rem; color: var(--muted); }
  .result-desc { color: #374151; font-size: 0.9rem; margin: 0.3rem 0; }
  .result-attrs { font-family: var(--mono); font-size: 0.8rem; color: var(--muted);
                  margin: 0.3rem 0; word-break: break-word; }
  table.scores { margin: 0; font-size: 0.85rem; width: 100%; }
  table.scores th, table.scores td { padding: 0.2rem 0.4rem; text-align: left; }
  table.scores th { color: var(--muted); font-weight: 500; }
  table.scores td.value { font-family: var(--mono); text-align: right; }
  table.scores tr.relevance th, table.scores tr.relevance td { font-weight: 600;
        border-bottom: 1px solid var(--border); padding-bottom: 0.35rem; }
  .empty-results { color: var(--muted); font-style: italic; padding: 0.5rem 0; }
  @media (max-width: 720px) {
    .result { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<h1>Relevance test report</h1>
<div class="meta">
  Engine: <code>{{ engine_name }}</code> &middot;
  Run ID: <code>{{ test_run_id }}</code>
</div>

<div class="summary">
  <table>
    <thead>
      <tr><th>Category</th><th>Passed</th><th>Failed</th><th>Total</th><th>Pass rate</th></tr>
    </thead>
    <tbody>
      {% for row in summary_rows %}
        <tr><td>{{ row.category }}</td><td>{{ row.passed }}</td><td>{{ row.failed }}</td><td>{{ row.total }}</td><td>{{ row.pass_rate }}</td></tr>
      {% endfor %}
      <tr class="total">
        <td>TOTAL</td><td>{{ overall.passed }}</td><td>{{ overall.failed }}</td><td>{{ overall.total }}</td><td>{{ overall.pass_rate }}</td>
      </tr>
    </tbody>
  </table>
</div>

{% for category, tests in tests_by_category %}
  <h2>{{ category }} <span style="color: var(--muted); font-weight: normal; font-size: 0.9rem;">({{ tests|length }} tests)</span></h2>
  {% for t in tests %}
    <details class="test"{% if not t.passed %} open{% endif %}>
      <summary>
        <span class="badge {{ 'pass' if t.passed else 'fail' }}">{{ 'PASS' if t.passed else 'FAIL' }}</span>
        <span>{{ t.test_name }}</span>
        <span class="query">{{ t.search_terms }}</span>
      </summary>
      <div class="test-body">
        <div class="test-meta">{{ t.description }}</div>

        {% if t.diagnosis %}
          <div class="diagnosis">{{ t.diagnosis }}</div>
        {% endif %}

        {% if t.note %}
          <div class="note">{{ t.note }}</div>
        {% endif %}

        {% if t.results %}
          <div class="results-heading">Search results</div>
          {% for r in t.results %}
            <div class="result">
              <div class="result-main">
                <div class="result-header">
                  <span class="rank">#{{ loop.index }}</span>
                  <span class="title">{{ r.title }}</span>
                  <span class="id">{{ r.id }}</span>
                </div>
                {% if r.description %}<div class="result-desc">{{ r.description }}</div>{% endif %}
                {% if r.attributes %}<div class="result-attrs">{{ r.attributes }}</div>{% endif %}
              </div>
              {% if r.scores %}
                <table class="scores">
                  <tr class="relevance"><th>relevance</th><td class="value">{{ r.relevance }}</td></tr>
                  {% for feature, value in r.scores %}
                    <tr><th>{{ feature }}</th><td class="value">{{ value }}</td></tr>
                  {% endfor %}
                </table>
              {% endif %}
            </div>
          {% endfor %}
        {% else %}
          <div class="empty-results">No results returned.</div>
        {% endif %}
      </div>
    </details>
  {% endfor %}
{% endfor %}

</body>
</html>
"""


def _format_score(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _format_attributes(attrs: dict | None) -> str:
    if not attrs:
        return ""
    return ", ".join(f"{k}={v}" for k, v in attrs.items())


def render_test_results_html(
    test_results: list,
    engine_name: str,
    test_run_id: str,
) -> str:
    """
    Render a list of TestResult objects as a self-contained HTML report.

    :param test_results: TestResult objects (with optional ``debug_info``).
    :param engine_name: Display name of the search engine.
    :param test_run_id: Identifier for the test run.
    :returns: Complete HTML document as a string.
    """
    # Lazy import to avoid a circular import (relevance_tests.__init__
    # imports from this module).
    from relevance_tests import calculate_test_result_metrics

    metrics = calculate_test_result_metrics(test_results)

    excluded_keys = {"overall", "macro_average"}
    summary_rows = []
    for category in sorted(k for k in metrics.keys() if k not in excluded_keys):
        cat = metrics[category]
        pass_rate = f"{(cat['pass_rate'] * 100):.1f}%" if cat["total"] else "N/A"
        summary_rows.append(
            {
                "category": category,
                "passed": cat["passed"],
                "failed": cat["failed"],
                "total": cat["total"],
                "pass_rate": pass_rate,
            }
        )

    overall_metrics = metrics["overall"]
    overall_pass_rate = (
        f"{(overall_metrics['pass_rate'] * 100):.1f}%"
        if overall_metrics["total"]
        else "N/A"
    )
    overall = {
        "passed": overall_metrics["passed"],
        "failed": overall_metrics["failed"],
        "total": overall_metrics["total"],
        "pass_rate": overall_pass_rate,
    }

    # Group test results by category; failed first within each category.
    by_category: dict[str, list] = {}
    for r in test_results:
        cat = r.test_case.category or "uncategorized"
        by_category.setdefault(cat, []).append(r)

    tests_by_category: list[tuple[str, list[dict]]] = []
    for category in sorted(by_category.keys()):
        rendered = []
        # Failed tests first so domain experts see them immediately.
        sorted_results = sorted(by_category[category], key=lambda r: r.passed)
        for tr in sorted_results:
            rendered.append(_render_test_entry(tr))
        tests_by_category.append((category, rendered))

    env = Environment(autoescape=select_autoescape(["html", "xml"]))
    template = env.from_string(_TEMPLATE)
    return template.render(
        engine_name=engine_name,
        test_run_id=test_run_id,
        summary_rows=summary_rows,
        overall=overall,
        tests_by_category=tests_by_category,
    )


def _render_test_entry(test_result) -> dict:
    """Project a TestResult into the dict shape consumed by the template."""
    tc = test_result.test_case
    diagnosis = (
        "" if test_result.passed else (tc.diagnose(test_result.search_results) or "")
    )

    # SearchComparisonTestCase runs two queries — debug info captured after the
    # call belongs to the *second* query while search_results are from the
    # *first*, so we don't align them.
    note = ""
    debug_info = test_result.debug_info
    if tc.name == "SearchComparisonTestCase":
        note = (
            "Per-result ranking scores are omitted for SearchComparisonTestCase: "
            "two queries are executed and the debug info would not align with "
            "the displayed results."
        )
        debug_info = None

    results_rendered = []
    for i, doc in enumerate(test_result.search_results):
        hit_debug = debug_info[i] if debug_info and i < len(debug_info) else None
        scores: list[tuple[str, str]] = []
        relevance_str = "—"
        if hit_debug is not None:
            sf = hit_debug.get("summaryfeatures") or {}
            for feature in SCORE_FEATURES:
                scores.append((feature, _format_score(sf.get(feature))))
            relevance_str = _format_score(hit_debug.get("relevance"))

        results_rendered.append(
            {
                "id": getattr(doc, "id", ""),
                "title": getattr(doc, "title", "") or "",
                "description": getattr(doc, "description", "") or "",
                "attributes": _format_attributes(getattr(doc, "attributes", None)),
                "scores": scores,
                "relevance": relevance_str,
            }
        )

    return {
        "test_name": tc.name,
        "search_terms": tc.search_terms,
        "description": tc.description,
        "passed": test_result.passed,
        "diagnosis": diagnosis,
        "note": note,
        "results": results_rendered,
    }
