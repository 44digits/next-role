from typing import Any

from .cli import run_config
from .config import parse_config
from .logging_utils import configure_logging


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    config = parse_config(event)
    summary = run_config(config, logger=configure_logging())
    if summary.exit_code:
        raise RuntimeError(f"Job fetcher completed with {summary.failures} failure(s).")
    return summary.as_dict()
