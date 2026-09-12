"""Error handling for Meta Ads MCP tools."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import requests

from burnr8.logging import log_tool_call, new_correlation_id
from burnr8.meta.client import MetaAdsApiError

P = ParamSpec("P")
R = TypeVar("R")


def handle_meta_ads_errors(fn: Callable[P, R]) -> Callable[P, R | dict]:
    """Log a Meta tool call and convert expected failures to safe MCP responses."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict:
        new_correlation_id()
        start = time.monotonic()
        raw_account_id = kwargs.get("account_id")
        account_id = str(raw_account_id) if raw_account_id is not None else None
        try:
            result = fn(*args, **kwargs)
            duration = time.monotonic() - start
            if isinstance(result, dict) and result.get("error"):
                log_tool_call(fn.__name__, account_id, duration, "error", f'msg="{result.get("message", "")}"')
            elif isinstance(result, dict) and result.get("warning"):
                log_tool_call(fn.__name__, account_id, duration, "warn", "confirm=false")
            else:
                log_tool_call(fn.__name__, account_id, duration, "ok")
            return result
        except MetaAdsApiError as ex:
            duration = time.monotonic() - start
            log_tool_call(
                fn.__name__, account_id, duration, "error", f"meta_code={ex.code} http_status={ex.status_code}"
            )
            return ex.as_dict()
        except requests.RequestException:
            duration = time.monotonic() - start
            message = "Could not reach the Meta Marketing API. Check the network connection and try again."
            log_tool_call(fn.__name__, account_id, duration, "error", "network_error=true")
            return {"error": True, "message": message}
        except (KeyError, ValueError, TypeError, IndexError) as ex:
            duration = time.monotonic() - start
            log_tool_call(fn.__name__, account_id, duration, "error", f'msg="{str(ex)[:200]}"')
            return {"error": True, "message": str(ex)[:500]}
        except OSError as ex:
            duration = time.monotonic() - start
            message = str(ex)[:500]
            log_tool_call(fn.__name__, account_id, duration, "error", f'msg="{message[:200]}"')
            return {"error": True, "message": message}

    return wrapper
