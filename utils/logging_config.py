"""
Structured JSON logging for production (VPS): easy grep/parse without extra PII.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional


# LogRecord implementation fields (version-dependent, e.g. taskName on 3.12) plus attributes that
# Formatter.format() adds; anything else on a record came from ``extra=`` and is kept.
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line; user_id, event and other ``extra=`` fields from LogRecord."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        uid: Optional[int] = getattr(record, "user_id", None)
        if uid is not None:
            payload["user_id"] = uid
        event: Optional[str] = getattr(record, "event", None)
        if event:
            payload["event"] = event
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in ("user_id", "event") or key in payload:
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, json_format: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)
