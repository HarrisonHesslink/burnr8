import functools
import time

from google.ads.googleads.errors import GoogleAdsException

from burnr8.logging import log_tool_call, new_correlation_id


def handle_google_ads_errors(fn):
    """Decorator that logs tool calls and catches GoogleAdsException and common errors."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        new_correlation_id()
        start = time.monotonic()
        customer_id = kwargs.get("customer_id") or (args[0] if args else None)
        try:
            result = fn(*args, **kwargs)
            duration = time.monotonic() - start

            # Check if the result itself is an error dict (validation failures)
            if isinstance(result, dict) and result.get("error"):
                log_tool_call(fn.__name__, customer_id, duration, "error", f"msg=\"{result.get('message', '')}\"")
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
        except GoogleAdsException as ex:
            duration = time.monotonic() - start
            errors = []
            for error in ex.failure.errors:
                err = {"message": error.message[:200], "code": str(error.error_code)}
                if error.location and error.location.field_path_elements:
                    err["field_path"] = [el.field_name for el in error.location.field_path_elements]
                errors.append(err)
            log_tool_call(
                fn.__name__, customer_id, duration, "error",
                f"request_id={ex.request_id} status={ex.error.code().name} msg=\"{errors[0]['message'][:100] if errors else ''}\"",
            )
            return {
                "error": True,
                "request_id": ex.request_id,
                "status": ex.error.code().name,
                "errors": errors,
            }
        except (KeyError, ValueError, TypeError) as ex:
            duration = time.monotonic() - start
            log_tool_call(fn.__name__, customer_id, duration, "error", f"msg=\"{ex}\"")
            return {
                "error": True,
                "message": str(ex),
            }
        except OSError as ex:
            duration = time.monotonic() - start
            # Don't leak full exception text — may contain paths or system info
            safe_msg = str(ex)[:200]
            log_tool_call(fn.__name__, customer_id, duration, "error", f"msg=\"{safe_msg}\"")
            return {
                "error": True,
                "message": safe_msg,
            }

    return wrapper
