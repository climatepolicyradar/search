"""Helpers for interacting with Weights & Biases"""

from typing import Any

import pandas as pd
import wandb
from wandb import Run

from relevance_tests import TestResult, calculate_test_result_metrics
from search import config
from search.aws import get_ssm_parameter
from search.document import Document
from search.engines import SearchEngine
from search.label import Label
from search.log import get_logger
from search.online_metrics import OnlineMetricResult
from search.passage import Passage

logger = get_logger(__name__)


class WandbSession:
    """Session for interacting with Weights & Biases (W&B)."""

    def __init__(
        self,
    ) -> None:
        """
        Initialise Weights & Biases session class.

        This doesn't connect to Weights & Biases until one of the public methods is
        called.
        """

        self.disable = config.DISABLE_WANDB

        if self.disable:
            logger.info(
                "WandbSession has been created with connection disabled. Pass an empty or false value to the env variable DISABLE_WANDB to enable W&B connection."
            )

        self.entity = config.WANDB_ENTITY
        self.offline_tests_project_prefix = config.WANDB_PROJECT_PREFIX_OFFLINE_TESTS
        self.online_metrics_project = config.WANDB_PROJECT_ONLINE_METRICS

        if not config.WANDB_SKIP_SSM_AUTH:
            logger.info(
                "Using Weights and Biases credentials from SSM. This will overwrite any login you have locally for the duration of the session."
            )
            self.api_key = get_ssm_parameter("WANDB_API_KEY")
        else:
            self.api_key = None

    def new_run(
        self,
        project: str,
        config: dict[str, Any] | None = None,
        job_type: str | None = None,
        group: str | None = None,
        **kwargs,
    ) -> Run:
        """
        Get a new W&B run.

        Extra kwargs are passed to wandb.init.
        """

        if self.api_key:
            wandb.login(
                key=self.api_key,
                relogin=False,
            )

        run = wandb.init(
            entity=self.entity,
            project=project,
            mode="disabled" if self.disable else "online",
            config=config,
            job_type=job_type,
            group=group,
            reinit=True,
            **kwargs,
        )

        return run

    def log_test_results(
        self,
        test_results: list[TestResult],
        primitive: type[Document | Label | Passage],
        search_engine: SearchEngine,
        run: Run | None = None,
    ) -> None:
        """
        Log search test results to Weights and Biases.

        :raises ValueError: if not all test results are from the same search engine.
        """

        if len(set(result.search_engine_id for result in test_results)) > 1:
            raise ValueError(
                "All test results passed to log_test_results must be from the same search engine."
            )

        primitive_name = primitive.__name__
        project_name = f"{self.offline_tests_project_prefix}_{primitive_name.lower()}"

        run = self.new_run(
            project=project_name,
            config={
                "primitive": primitive_name,
                "search_engine_id": search_engine.id,
                "search_engine": str(search_engine),
                "search_engine_name": search_engine.name,
            },
        )

        logger.info(
            f"Logging metrics for {len(test_results)} tests with primitive {primitive_name} to W&B"
        )

        metrics = calculate_test_result_metrics(test_results)
        categories = [k for k in metrics if k != "overall"]

        summary_metrics = {
            key: {k: v for k, v in cat_metrics.items() if k != "results"}
            for key, cat_metrics in metrics.items()
        }
        summary_metrics = {
            (f"category.{k}" if k != "overall" else k): v
            for k, v in summary_metrics.items()
        }
        run.summary.update(summary_metrics)

        metrics_by_category_table = pd.DataFrame(
            [{**metrics[cat], "category": cat} for cat in categories]
        )[["category", "passed", "failed", "total", "pass_rate"]]

        test_results_table = pd.DataFrame(
            [
                {
                    "test_case_name": r.test_case.name,
                    "category": r.test_case.category or "uncategorized",
                    "search_terms": r.test_case.search_terms,
                    "description": r.test_case.description,
                    "passed": r.passed,
                    "search_engine_id": str(r.search_engine_id),
                    "num_results": len(r.search_results),
                }
                for r in test_results
            ]
        )

        run.log(
            {
                "category_metrics": wandb.Table(dataframe=metrics_by_category_table),
                "individual_test_results": wandb.Table(dataframe=test_results_table),
            }
        )
        logger.info(
            f"Logged tables: metrics for {len(metrics_by_category_table)} categories, {len(test_results_table)} test results"
        )

        run.finish()

    def log_online_metric_result(
        self,
        online_metric_result: OnlineMetricResult,
    ) -> None:
        """Log a single online metric result to Weights & Biases."""

        # TODO: remove the query from the table / add canonical id for query and date/date range?
        # TODO: right now each run is for a single metric and creates a new table.  Do we want that?

        config = {"metric": online_metric_result.metric}
        config["date_from"] = online_metric_result.date_from
        if online_metric_result.date_to:
            config["date_to"] = online_metric_result.date_to

        run = self.new_run(
            project=self.online_metrics_project,
            config=config,
        )

        metric_model_dump = online_metric_result.model_dump()

        metric_table = wandb.Table(dataframe=pd.DataFrame([metric_model_dump]))

        run.log({"metric_table": metric_table})

        logger.info(f"Logged online metric '{online_metric_result.metric}' to W&B")

        run.finish()
