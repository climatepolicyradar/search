from pathlib import Path

from pydantic_settings import SettingsConfigDict

from search.engines.dev_vespa import Settings
from search.log import get_logger

logger = get_logger(__name__)


class EnvSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"), extra="allow"
    )


# @see: https://github.com/pydantic/pydantic-settings/issues/201
settings = EnvSettings()  # pyright: ignore[reportCallIssue]
logger.info(
    f"Search settings resolved: vespa_endpoint={settings.vespa_endpoint} "
    f"vespa_dev_instance_name={settings.vespa_dev_instance_name}"
)
