Help the user set up burnr8 credentials.

Ask which Burnr8 capability the user wants to configure: Google Ads, Meta Ads, Reddit Ads, or SEO Intelligence. Check the matching discovery tool (`list_accessible_accounts`, `meta_list_ad_accounts`, `reddit_list_businesses`, or `gsc_list_properties`) instead of assuming one credential proves every service is configured.

For Reddit, use `burnr8-reddit-setup` after the user registers `http://localhost:8765/callback` in Reddit Ads Manager → Business → Developer Portal. The helper uses a local callback, validates OAuth state, and saves credentials without exposing tokens in chat. It does not require Google credentials. See `docs/reddit-ads.md`, then restart the MCP server and use `reddit_list_businesses` / `reddit_list_ad_accounts`.

If it fails with a credentials error, tell the user:

1. Run this command in your terminal (type `! burnr8-setup` at the prompt — the `!` prefix runs it directly):

   ! burnr8-setup

2. The wizard will prompt for:
   - Google Ads developer token (from API Center in your Google Ads account)
   - OAuth2 client ID + secret (from Google Cloud Console)
   - Google Ads refresh token authorized for the Google Ads scope
   - Login customer ID (optional, for manager/MCC accounts)
   - Meta access token, app secret, account ID, and approved media directory (optional)
   - Search Console refresh token authorized for `webmasters.readonly`, default property, and PageSpeed/CrUX API keys (optional)

3. Credentials are saved to ~/.burnr8/.env with restricted permissions.

4. After setup completes, restart the MCP server and try the matching discovery tool. Search Console and Google Ads use separate refresh tokens because their OAuth scopes differ.
