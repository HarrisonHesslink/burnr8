"""Safe MCP error responses and existing Burnr8 usage logging."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import requests

from burnr8.logging import log_tool_call, new_correlation_id
from burnr8.reddit.client import RedditAdsApiError

P = ParamSpec("P")
R = TypeVar("R")


def handle_reddit_errors(fn: Callable[P, R]) -> Callable[P, R | dict[str, object]]:
    """Log outcomes, never request bodies, tokens, or raw network errors."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, object]:
        new_correlation_id()
        start = time.monotonic()
        result: R | dict[str, object]
        try:
            result = fn(*args, **kwargs)
        except RedditAdsApiError as ex:
            result = {"error": True, "message": str(ex), "http_status": ex.status_code}
        except requests.RequestException:
            result = {"error": True, "message": "Could not reach the Reddit Ads API. Check the connection."}
        except (ValueError, OSError) as ex:
            result = {"error": True, "message": str(ex)[:500]}
        status = "ok"
        if isinstance(result, dict):
            status = "error" if result.get("error") else "warn" if result.get("warning") else "ok"
        log_tool_call(fn.__name__, None, time.monotonic() - start, status)
        return result

    return wrapper
