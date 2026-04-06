Help the user set up burnr8 credentials.

Check if credentials are configured by calling get_api_usage. If it works, tell the user burnr8 is already configured.

If it fails with a credentials error, tell the user:

1. Run this command in your terminal (type `! burnr8-setup` at the prompt — the `!` prefix runs it directly):

   ! burnr8-setup

2. The wizard will prompt for:
   - Google Ads developer token (from API Center in your Google Ads account)
   - OAuth2 client ID + secret (from Google Cloud Console)
   - Refresh token (the wizard can generate one via browser OAuth)
   - Login customer ID (optional, for manager/MCC accounts)

3. Credentials are saved to ~/.burnr8/.env with restricted permissions.

4. After setup completes, try: list_accessible_accounts
