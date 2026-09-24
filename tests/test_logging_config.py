"""JsonFormatter keeps application-specific extra fields."""
from __future__ import annotations

import io
import json
import logging
from typing import Callable, Iterator

import pytest

from utils.logging_config import JsonFormatter


@pytest.fixture
def emit() -> Iterator[Callable[..., dict[str, object]]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test_logging_config")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)

    def _emit(msg: str = "hello", **kwargs: object) -> dict[str, object]:
        stream.truncate(0)
        stream.seek(0)
        logger.info(msg, **kwargs)
        return json.loads(stream.getvalue())

    yield _emit
    logger.removeHandler(handler)


def test_extra_fields_are_preserved(emit) -> None:
    out = emit(
        extra={
            "user_id": 7,
            "event": "idle_route",
            "fsm_state": "none",
            "intent": "small_talk",
            "ai_called": False,
            "retries": 3,
        }
    )
    assert out["user_id"] == 7
    assert out["event"] == "idle_route"
    assert out["fsm_state"] == "none"
    assert out["intent"] == "small_talk"
    assert out["ai_called"] is False
    assert out["retries"] == 3


def test_standard_logrecord_fields_are_not_leaked(emit) -> None:
    out = emit("plain message", extra={"user_id": 1, "handler_path": "x"})
    assert out["message"] == "plain message"
    assert set(out) == {"ts", "level", "logger", "message", "user_id", "handler_path"}


def test_base_fields_are_not_overwritten(emit) -> None:
    out = emit(extra={"level": "spoofed", "logger": "spoofed", "ts": "spoofed"})
    assert out["level"] == "INFO"
    assert out["logger"] == "test_logging_config"
    assert out["ts"] != "spoofed"


def test_non_serializable_extra_does_not_break_logging(emit) -> None:
    class Odd:
        def __repr__(self) -> str:
            return "<Odd>"

    out = emit(extra={"odd": Odd(), "nested": {"a": [1, 2]}, "user_id": None})
    assert out["odd"] == "<Odd>"
    assert out["nested"] == {"a": [1, 2]}
    assert "user_id" not in out


def test_exc_info_still_included(emit) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        out = emit("failed", exc_info=True, extra={"event": "error"})
    assert "ValueError: boom" in out["exc_info"]
    assert out["event"] == "error"
