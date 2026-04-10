import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from burnr8.logging import log_tool_call, new_correlation_id

P = ParamSpec("P")
R = TypeVar("R")

__all__ = ["handle_google_ads_errors"]


def handle_google_ads_errors(fn: Callable[P, R]) -> Callable[P, R | dict]:
    """Decorator that logs tool calls and catches GoogleAdsException and common errors."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict:
        new_correlation_id()
        start = time.monotonic()
        _raw_cid = kwargs.get("customer_id") or (args[0] if args else None)
        customer_id: str | None = str(_raw_cid) if _raw_cid is not None else None
        try:
            result = fn(*args, **kwargs)
            duration = time.monotonic() - start

            # Check if the result itself is an error dict (validation failures)
            if isinstance(result, dict) and result.get("error"):
                log_tool_call(fn.__name__, customer_id, duration, "error", f'msg="{result.get("message", "")}"')
            elif isinstance(result, dict) and result.get("warning"):
                log_tool_call(fn.__name__, customer_id, duration, "warn", "confirm=false")
            else:
                detail = ""
                if isinstance(result, list):
                    detail = f"rows={len(result)}"
                elif isinstance(result, dict) and "added" in result:
                    detail = f"added={result['added']}"
                log_tool_call(fn.__name__, customer_id, duration, "ok", detail)

            return result
        except Exception as ex:
            duration = time.monotonic() - start

            # Lazy import to avoid loading SDK at startup
            from google.ads.googleads.errors import GoogleAdsException

            if isinstance(ex, GoogleAdsException):
                errors = []
                for error in ex.failure.errors:
                    err = {"message": error.message[:200], "code": str(error.error_code)}
                    if error.location and error.location.field_path_elements:
                        err["field_path"] = [el.field_name for el in error.location.field_path_elements]
                    errors.append(err)
                log_tool_call(
                    fn.__name__,
                    customer_id,
                    duration,
                    "error",
                    f'request_id={ex.request_id} status={ex.error.code().name} msg="{errors[0]["message"][:100] if errors else ""}"',
                )
                return {
                    "error": True,
                    "message": errors[0]["message"] if errors else "Unknown Google Ads API error",
                    "request_id": ex.request_id,
                    "status": ex.error.code().name,
                    "errors": errors,
                }
            elif isinstance(ex, (KeyError, ValueError, TypeError, IndexError)):
                log_tool_call(fn.__name__, customer_id, duration, "error", f'msg="{ex}"')
                return {
                    "error": True,
                    "message": str(ex),
                }
            elif isinstance(ex, OSError):
                # Don't leak full exception text — may contain paths or system info
                safe_msg = str(ex)[:200]
                log_tool_call(fn.__name__, customer_id, duration, "error", f'msg="{safe_msg}"')
                return {
                    "error": True,
                    "message": safe_msg,
                }
            else:
                # Catch gRPC transport errors (timeout, unavailable, etc.)
                # These lack GoogleAdsFailure metadata so aren't GoogleAdsException
                import grpc

                if isinstance(ex, grpc.RpcError):
                    code = ex.code()
                    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
                        msg = "Google Ads API request timed out. Try a narrower date range or add a LIMIT clause."
                    else:
                        msg = f"Google Ads API RPC error: {code.name}"
                    log_tool_call(fn.__name__, customer_id, duration, "error", f"grpc_status={code.name}")
                    return {"error": True, "message": msg}
                raise

    return wrapper
