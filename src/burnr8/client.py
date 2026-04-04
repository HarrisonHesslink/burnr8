import os
import threading

from google.ads.googleads.client import GoogleAdsClient

_client: GoogleAdsClient | None = None
_client_lock = threading.Lock()


def get_client() -> GoogleAdsClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
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
