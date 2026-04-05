from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.ads.googleads.client import GoogleAdsClient

_client: GoogleAdsClient | None = None
_client_lock = threading.Lock()


_REQUIRED_VARS = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
]

__all__ = ["get_client"]


def get_client() -> GoogleAdsClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                from google.ads.googleads.client import GoogleAdsClient

                missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
                if missing:
                    raise OSError(
                        f"Missing required credentials: {', '.join(missing)}. "
                        "Run 'burnr8-setup' to configure, or set these environment variables."
                    )
                config = {
                    "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
                    "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
                    "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
                    "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
                    "use_proto_plus": True,
                }
                login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
                if login_customer_id:
                    config["login_customer_id"] = login_customer_id.replace("-", "")
                _client = GoogleAdsClient.load_from_dict(config_dict=config, version="v23")
    return _client
