import logging
import os
import sys
from collections.abc import Mapping
from uuid import uuid4

from .adapters import AdapterRegistry
from .api_client import JobImportClient
from .config import ConfigurationError, FetcherConfig, load_config_json
from .logging_utils import configure_logging, log_event
from .models import RunSummary
from .runner import JobFetcher


def build_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry()


def run_config(
    config: FetcherConfig,
    *,
    environment: Mapping[str, str] | None = None,
    adapters: AdapterRegistry | None = None,
    logger: logging.Logger | None = None,
    run_id: str | None = None,
) -> RunSummary:
    if environment is None:
        environment = os.environ
    logger = logger or configure_logging()
    api_client = JobImportClient.from_environment(dict(environment))
    runner = JobFetcher(
        config,
        adapters or build_adapter_registry(),
        api_client,
        logger,
        run_id=run_id,
    )
    return runner.run()


def main() -> int:
    logger = configure_logging()
    run_id = str(uuid4())
    try:
        config = load_config_json(sys.stdin.read())
    except ConfigurationError as error:
        log_event(
            logger,
            logging.ERROR,
            "configuration_failed",
            run_id=run_id,
            error=str(error),
        )
        return 2
    try:
        summary = run_config(config, logger=logger, run_id=run_id)
    except ConfigurationError as error:
        log_event(
            logger,
            logging.ERROR,
            "startup_failed",
            run_id=run_id,
            error=str(error),
        )
        return 2
    return summary.exit_code
