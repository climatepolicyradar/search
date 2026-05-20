# Document-topic relevance

See
[Notion](https://www.notion.so/climatepolicyradar/Idea-Evals-for-document-relevance-to-topics-3219109609a4802eae10e760cbf02bbc)
for details.

## Running evaluation

1. Run `load_dataset.py` on a CSV exported from
   [this Google Sheet](https://docs.google.com/spreadsheets/d/11VqkHR-F3k3UqEFp_uWX8_62kI5waYIomnh_ZSh5RGY/edit?gid=1208684289#gid=1208684289)
   to create a ground truth dataset with document and topic metadata enriched
   from Vespa. Vespa is local by default
2. Run `evaluate_predictors.py` with no arguments. This will evaluate the
   predictors specified in the script and output results a file.

Metrics are stored in [PREDICTOR_METRICS.md](./PREDICTOR_METRICS.md).
