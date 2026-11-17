import logging
import os
import sys
from collections.abc import Mapping
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

from .adapters import AdapterRegistry
from .api_client import JobImportClient
from .config import ConfigurationError, FetcherConfig, load_config_json
from .logging_utils import configure_logging, log_event
from .models import RunSummary
from .runner import JobFetcher


def build_adapter_registry(
    adapter_directory: Path | None = None,
) -> AdapterRegistry:
    registry = AdapterRegistry()
    if adapter_directory is None:
        adapter_directory = Path(__file__).resolve().parents[2] / "adapters"
    if not adapter_directory.is_dir():
        return registry

    for path in sorted(adapter_directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"_job_fetcher_adapter_{path.stem}"
        spec = spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ConfigurationError(f"Cannot load local adapter module {path.name!r}.")
        module = module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (ImportError, OSError, SyntaxError) as error:
            raise ConfigurationError(
                f"Cannot import local adapter module {path.name!r}: {error}"
            ) from error

        register = getattr(module, "register", None)
        if not callable(register):
            raise ConfigurationError(
                f"Local adapter module {path.name!r} must define register(registry)."
            )
        register(registry)
    return registry


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
