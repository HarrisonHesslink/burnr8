"""Safe error handling for SEO MCP tools."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import requests

from burnr8.logging import log_tool_call, new_correlation_id
from burnr8.seo.client import GoogleSeoApiError

P = ParamSpec("P")
R = TypeVar("R")


def handle_seo_errors(fn: Callable[P, R]) -> Callable[P, R | dict]:
    """Log an SEO tool call and convert expected failures to safe responses."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict:
        new_correlation_id()
        start = time.monotonic()
        raw_property = kwargs.get("property_url")
        property_label = str(raw_property) if raw_property is not None else None
        try:
            result = fn(*args, **kwargs)
            duration = time.monotonic() - start
            if isinstance(result, dict) and result.get("error"):
                log_tool_call(fn.__name__, property_label, duration, "error", "seo_error=true")
            elif isinstance(result, dict) and result.get("warning"):
                log_tool_call(fn.__name__, property_label, duration, "warn")
            else:
                log_tool_call(fn.__name__, property_label, duration, "ok")
            return result
        except GoogleSeoApiError as ex:
            log_tool_call(
                fn.__name__,
                property_label,
                time.monotonic() - start,
                "error",
                f"service={ex.service} http={ex.status_code}",
            )
            return ex.as_dict()
        except requests.RequestException:
            log_tool_call(fn.__name__, property_label, time.monotonic() - start, "error", "network_error=true")
            return {"error": True, "message": "Could not reach the Google SEO API. Check the network and try again."}
        except (KeyError, ValueError, TypeError, IndexError, OSError) as ex:
            message = str(ex)[:500]
            log_tool_call(fn.__name__, property_label, time.monotonic() - start, "error", "validation_error=true")
            return {"error": True, "message": message}
        except Exception as ex:
            # search_demand_gap also calls Google Ads; keep its SDK and gRPC
            # failures structured without weakening unexpected-error visibility.
            from google.ads.googleads.errors import GoogleAdsException

            if isinstance(ex, GoogleAdsException):
                errors = []
                for error in ex.failure.errors:
                    item = {"message": error.message[:200], "code": str(error.error_code)}
                    if error.location and error.location.field_path_elements:
                        item["field_path"] = [part.field_name for part in error.location.field_path_elements]
                    errors.append(item)
                message = errors[0]["message"] if errors else "Unknown Google Ads API error"
                log_tool_call(fn.__name__, property_label, time.monotonic() - start, "error", "google_ads_error=true")
                return {
                    "error": True,
                    "message": message,
                    "request_id": ex.request_id,
                    "status": ex.error.code().name,
                    "errors": errors,
                }

            import grpc

            if isinstance(ex, grpc.RpcError):
                code = ex.code()
                message = (
                    "Google Ads API request timed out. Try a narrower date range."
                    if code == grpc.StatusCode.DEADLINE_EXCEEDED
                    else f"Google Ads API RPC error: {code.name}"
                )
                log_tool_call(fn.__name__, property_label, time.monotonic() - start, "error", f"grpc={code.name}")
                return {"error": True, "message": message}
            raise

    return wrapper
