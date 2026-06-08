# Document-topic relevance

See
[Notion](https://www.notion.so/climatepolicyradar/Idea-Evals-for-document-relevance-to-topics-3219109609a4802eae10e760cbf02bbc)
for details.

## Running evaluation

Install the optional Snowflake dependency first: `uv sync --extra research`.

1. Run `load_dataset.py` on a CSV exported from
   [this Google Sheet](https://docs.google.com/spreadsheets/d/11VqkHR-F3k3UqEFp_uWX8_62kI5waYIomnh_ZSh5RGY/edit?gid=1208684289#gid=1208684289)
   to create a ground truth dataset. Documents and topics are enriched from
   Vespa (local by default), and each (document, topic) pair is enriched with
   passage-level mentions from Snowflake (`UNIFIED_PASSAGE_TOPICS` joined to
   `PIPELINE_PASSAGES_V1`) via the `local_dev` connection in
   `~/.snowflake/connections.toml`. Pass `--skip-snowflake` to leave mentions
   empty if you only need the Vespa enrichment.
2. Run `evaluate_predictors.py` with no arguments. This will evaluate the
   predictors specified in the script and output results a file.

Predictors are continuous-feature-with-thresholds (`ThresholdPredictor`): each
computes a signal (mention count, density, max mentions per page, earliest
mention) and maps it to a `{0, 1, 2}` score via two thresholds.

Metrics are stored in [PREDICTOR_METRICS.md](./PREDICTOR_METRICS.md).
