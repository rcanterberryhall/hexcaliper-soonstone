"""Structured JSON logging for soonstone.

A single `JsonFormatter` formats records as one JSON object per line. Any
fields attached to a LogRecord via `extra={...}` (e.g. job name, counts)
pass through to the JSON output. `configure_logging` is idempotent — calling
it twice does not double-attach handlers.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Standard LogRecord attributes that we don't want to copy into the JSON
# output (we either rename them or omit them). Anything not in this set is
# treated as a caller-provided extra field.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}

_HANDLER_MARKER = "__soonstone_json_handler__"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            handler.setLevel(level.upper())
            return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(level.upper())
    setattr(handler, _HANDLER_MARKER, True)
    root.addHandler(handler)
