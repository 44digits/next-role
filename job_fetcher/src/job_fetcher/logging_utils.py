import json
import logging
import sys
from datetime import datetime, timezone
from typing import TextIO


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            "context": getattr(record, "event_fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(stream: TextIO | None = None) -> logging.Logger:
    logger = logging.getLogger("job_fetcher")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: object,
) -> None:
    logger.log(level, event, extra={"event_fields": fields})
