"""Helpers for interacting with Weights & Biases"""

from datetime import date
from typing import Any

import wandb
from wandb import Run

from search import config
from search.aws import get_ssm_parameter
from search.log import get_logger
from search.online_metrics import OnlineMetricResult

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
        self.online_metrics_project = config.WANDB_PROJECT_ONLINE_METRICS

        if not config.WANDB_SKIP_SSM_AUTH and not self.disable:
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

    def log_online_metric_results(
        self,
        results: list[OnlineMetricResult],
        date_from: date,
        date_to: date | None = None,
        retention_date: date | None = None,
    ) -> None:
        """Log a list of online metric results to Weights & Biases."""

        config: dict[str, date | int] = {"date_from": date_from}
        if date_to:
            config["date_to"] = date_to
        if retention_date:
            config["retention_anchor_date"] = retention_date
        config["calendar_month"] = date_from.month
        config["year"] = date_from.year
        run = self.new_run(
            project=self.online_metrics_project,
            config=config,
        )

        for result in results:
            result_name = result.metric
            result_dict = result.model_dump(mode="python")
            result_dict = {
                f"{result_name}.{k}": v for k, v in result_dict.items() if k != "metric"
            }

            run.summary.update(result_dict)

        logger.info(f"Logged {len(results)} online metrics as summary to W&B")
        run.finish()
