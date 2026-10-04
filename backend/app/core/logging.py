"""Logging setup: one line per event, two formats.

`LOG_FORMAT=text` (default outside production) is for humans reading a
terminal. `LOG_FORMAT=json` (default in production) emits one JSON object per
line — `ts`, `level`, `logger`, `message` plus known request fields — so a log
shipper can parse it without regexes. `auto` picks json in production and text
otherwise.

Request fields reach the formatter through `logger.info(msg, extra={...})`;
only the allow-list in `EXTRA_FIELDS` is promoted, so arbitrary record
attributes never leak into the JSON payload.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import settings

TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Fields promoted from LogRecord extras (set via `logger.info(..., extra=...)`).
EXTRA_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "client_ip",
    "scope",
    "exception",
)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def resolve_log_format() -> str:
    choice = settings.log_format.strip().lower()
    if choice == "auto":
        return "json" if settings.is_production else "text"
    return choice


def setup_logging() -> None:
    """(Re)wire our root handler; safe to call again after a settings change.

    Only handlers installed by us are replaced — pytest's and uvicorn's
    handlers must survive re-entry.
    """
    formatter: logging.Formatter
    if resolve_log_format() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(TEXT_FORMAT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler._aic_root = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    root.handlers[:] = [h for h in root.handlers if not getattr(h, "_aic_root", False)]
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
