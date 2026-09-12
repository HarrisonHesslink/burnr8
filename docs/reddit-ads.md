# Reddit Ads in Burnr8

Burnr8 provides 23 tools for Reddit Ads API v3: account discovery, inventory, community targeting search, CSV reporting, media imports, image/video ad posts, paused campaign/ad-group/ad creation, delivery status, and budget controls. No Reddit credentials are needed to start the MCP server or use another provider.

## Connect a Reddit Ads account

1. Sign into [Reddit Ads Manager](https://ads.reddit.com). A business admin with a verified Reddit account can create an application in **Business → Developer Portal → Add Apps → Create an app**.
2. Name the app for this integration, such as `StudyWithLily Burnr8`, and register **exactly** `http://localhost:8765/callback` as its redirect URL. Save the app ID and secret locally.
3. From a terminal on the same machine as your browser, run:

   ```bash
   burnr8-reddit-setup
   ```

   For a source checkout, `./.venv/bin/python -m burnr8.reddit.auth` works too. If port 8765 is occupied, use `--redirect-uri http://localhost:8766/callback` and register that exact URL in Reddit first.

4. Enter the app ID and secret when prompted. The secret is hidden. The helper opens Reddit's consent page, waits up to five minutes for the local callback, checks its state, exchanges the code, and saves credentials to `~/.burnr8/.env` with mode `0600`. It preserves existing Google, Meta, SEO and other settings. It requests only `adsread` and `adsedit` with permanent authorization.
5. Restart the MCP server so it loads the new environment and tools. Call `reddit_list_businesses`, then `reddit_list_ad_accounts` with a returned business ID. Set `REDDIT_AD_ACCOUNT_ID` to the selected `a2_...` or `t2_...` ID, or supply `account_id` on each tool call.

The helper stores:

```dotenv
REDDIT_CLIENT_ID=your-app-id
REDDIT_CLIENT_SECRET=your-app-secret
REDDIT_REFRESH_TOKEN=your-refresh-token
REDDIT_AD_ACCOUNT_ID=a2_youraccount
```

The account ID is selected in step 5, not written automatically by OAuth. `REDDIT_USER_AGENT` is optional; use a descriptive identifier for your application. `REDDIT_ACCESS_TOKEN` is an optional short-lived override for diagnostics. Remove it to use automatic refresh-token authentication. The setup helper removes a stale access-token override when saving a new grant.

Official references: [developer application setup](https://ads-api.reddit.com/docs/v3/guides/quick-start/create-dev-app), [OAuth](https://ads-api.reddit.com/docs/v3/guides/quick-start/authenticate), [API specification](https://ads-api.reddit.com/api/v3/openapi.json).

## Tools

| Tool | Behavior |
| --- | --- |
| `reddit_list_businesses` | Businesses authorized to this OAuth identity |
| `reddit_list_ad_accounts` | Ad accounts belonging to a selected business |
| `reddit_get_ad_account` | Account currency, timezone, approval and attribution settings |
| `reddit_list_campaigns` | Campaign inventory, status and budget configuration |
| `reddit_list_ad_groups` | Ad-group targeting, schedules, budgets and bid configuration |
| `reddit_list_ads` | Ad inventory and delivery/review state |
| `reddit_search_communities` | Ads API community targeting discovery; no post/user scraping |
| `reddit_get_report` | One performance page, exported to CSV with explicit continuation |
| `reddit_create_campaign` | Preview/create a paused standard campaign with a required lifetime spend cap |
| `reddit_set_status` | Preview/apply `ACTIVE` or `PAUSED` to an owned campaign, ad group or ad |
| `reddit_update_ad_group_budget` | Preview/change an existing USD ad-group daily budget |
| `reddit_update_campaign_spend_cap` | Preview/change a USD lifetime campaign cap with ad-group budgeting |
| `reddit_list_profiles` | Posting profiles linked to the selected ad account |
| `reddit_list_pixels` | Linked pixel IDs required for new ad groups |
| `reddit_get_pixel_health` | Last received event timestamps for an account-linked pixel; ingestion is separate from attribution |
| `reddit_list_creative_assets` | A linked profile's asset library and hosted media URLs |
| `reddit_list_ad_posts` | Promoted structured posts for creative review and interrupted-write reconciliation |
| `reddit_create_ad_group` | Preview/create a paused manual ad group with explicit geography, pixel, budget and schedule |
| `reddit_upload_media` | Preview/import an image or video from public HTTPS URLs |
| `reddit_get_media_upload` | Poll the accepted upload ID; return the processed asset when ready |
| `reddit_create_ad_post` | Preview/create an image/video ad-post job from an active profile asset |
| `reddit_get_ad_post_job` | Poll a post job and verify the completed post belongs to the selected profile |
| `reddit_create_ad` | Preview/create a paused ad with matching destination URL, UTMs and a placement preview link |

## Prepare a campaign

Call `reddit_get_ad_account` to check the account, and `reddit_search_communities` to inspect available targeting options. Then preview a campaign:

```json
{
  "name": "StudyWithLily Reddit pilot",
  "objective": "CLICKS",
  "spend_cap_dollars": 100,
  "account_id": "a2_youraccount",
  "confirm": false
}
```

Repeat `reddit_create_campaign` with `confirm=true` after reviewing the plan. Keep the returned campaign ID for the ad-group step below.

Creation supports the existing `CLICKS`, `CONVERSIONS` and `IMPRESSIONS` objectives. Reddit's [September 2026 migration guide](https://ads-api.reddit.com/docs/v3/guides/programs/campaign/campaign-objective-migration) says the legacy objective names will remain supported. Campaign budget optimization and Reddit Max campaign creation are outside this version's scope.

## Prepare a complete image or video ad

All examples are previews. Use real IDs from discovery and choose future UTC dates. Repeat a reviewed write with `confirm=true` to submit it; retain every returned ID.

1. Call `reddit_list_profiles` and `reddit_list_pixels`. Choose the linked profile that should appear as the advertiser. Profile access elsewhere in the business is insufficient: creation checks its link to the selected account. Reddit requires `conversion_pixel_id` for all new ad groups as of July 13, 2026. A listed pixel does not prove it is installed or receiving events.
2. Call `reddit_create_ad_group` with the campaign ID:

   ```json
   {
     "name": "US nursing students",
     "campaign_id": "your_campaign_id",
     "daily_budget_dollars": 5,
     "conversion_pixel_id": "your_linked_pixel_id",
     "geolocations": ["US"],
     "communities": ["StudentNurse"],
     "starts_at": "2026-09-10T16:00:00Z",
     "ends_at": "2026-09-17T16:00:00Z",
     "confirm": false
   }
   ```

   Check communities with `reddit_search_communities` first; their availability can change. Community targeting is an audience setting, not a promise of placement only inside that subreddit. Targeting expansion is explicitly off. Placements default to `FEED`; `COMMENTS_PAGE` is also supported. Omitting `communities` allows geography-only targeting. `excluded_communities` is optional. Schedules use explicit UTC start/end times; these tools do not modify other campaigns' schedules.

   `CLICKS` and `CONVERSIONS` use `BIDLESS` with CPC by default. Supplying `bid_dollars` selects manual bidding. `CONVERSIONS` requires an explicit goal: `PAGE_VISIT`, `ADD_TO_CART`, `PURCHASE`, `LEAD` or `SIGN_UP`. `IMPRESSIONS` requires a manual CPM bid of $3.50–$100.
3. Call `reddit_upload_media` to import an image:

   ```json
   {
     "profile_id": "t2_yourprofile",
     "name": "NCLEX pilot image",
     "media_type": "IMAGE",
     "media_url": "https://your-site.example/ads/nclex-pilot.png",
     "confirm": false
   }
   ```

   Reddit downloads media from a hosted HTTPS URL. This tool does not accept local file paths or base64 and does not publish local files to a hosting service. For video, use `media_type=VIDEO`, a hosted video URL and a required image `poster_url`. Reddit performs format, dimensions and processing validation. BurnR8 does not fetch these URLs or send OAuth credentials to media hosts.

   The confirmed call returns `upload_id` and a client `reference_id`, not a finished asset. Poll `reddit_get_media_upload` with `profile_id` and `upload_id` until `ready=true`. Keep the returned `asset.id`. If processing fails, inspect that upload before trying a corrected asset.
4. Call `reddit_create_ad_post`:

   ```json
   {
     "profile_id": "t2_yourprofile",
     "headline": "Practice for the NCLEX",
     "destination_url": "https://your-site.example/nclex?utm_source=reddit&utm_medium=paid_social&utm_campaign=pilot",
     "media_asset_id": "your_active_asset_id",
     "call_to_action": "Sign Up",
     "confirm": false
   }
   ```

   The active media asset must belong to that profile. Image and video posts are supported. Video uses the imported poster; an optional active image `thumbnail_asset_id` can override it. Comments default off and Redditor Highlights is explicitly opted out, preserving the supplied creative. The post can have a Reddit URL before ads run; it is not a private draft. This tool does not choose a community or publish a community reply.

   The confirmed call returns `job_id`. Poll `reddit_get_ad_post_job` with that ID and `profile_id`. A successful job is followed by a post read that verifies the profile. Use the returned `post_id` only when `ready=true`. Pending jobs are polled by ID, not recreated.
5. Call `reddit_create_ad` with `name`, `ad_group_id`, `profile_id` and `post_id`. Review the preview, then confirm. The tool copies the post's destination URL exactly, including UTMs, and creates the ad as `PAUSED`. It requests a placement preview link valid for seven days by default; an explicit `preview_expires_at` within the next 30 days can be supplied. Successful read-back includes Reddit's `preview_url` when available and the post URL as a fallback. Reddit may require initial test-URL generation in Ads Manager, and preview delivery can lag; the tool reports a missing placement link. See [Reddit's preview guide](https://ads-api.reddit.com/docs/v3/guides/programs/campaign/preview-an-ad). `verified=true` confirms the requested saved fields; it does not mean the ad is approved or delivering.

Activation remains a separate `reddit_set_status` action for the relevant campaign, ad group and ad. Conversion forwarding and website pixel installation are not included in these creation tools. Confirm signup and first-payment measurement before interpreting conversion-optimized delivery.

API references: [ad groups](https://ads-api.reddit.com/docs/v3/api/create-ad-group), [media imports](https://ads-api.reddit.com/docs/v3/api/create-creative-asset-uploads), [structured ad posts](https://ads-api.reddit.com/docs/v3/api/create-structured-post-creation-job), [ads](https://ads-api.reddit.com/docs/v3/api/create-ad).

## Budget and status controls

- All writes default to `confirm=false`. A preview performs validation and reads account state; it does not invoke a provider write or claim Reddit has accepted the proposed payload.
- Campaign, ad-group and ad creation always sends `configured_status=PAUSED`. Media uploads and post jobs have processing states instead of delivery states. Only `ACTIVE` and `PAUSED` are available through the delivery status tool.
- Budget tools require a USD account and convert dollars to **microcurrency (1 dollar = 1,000,000)**. Daily-budget creation/changes use `BURNR8_MAX_DAILY_BUDGET_DOLLARS`; manual CPC bids use the existing `BURNR8_MAX_CPC_BID_DOLLARS` limit. Lifetime campaign caps use `BURNR8_REDDIT_MAX_SPEND_CAP_DOLLARS`, defaulting to $1,000. These are local maximums, not budgets assigned automatically to campaigns.
- Daily-budget changes reject lifetime budgets and budgets controlled at campaign level. Campaign-cap changes require ad-group budgeting.
- Every mutation validates account ownership where an existing resource is involved. Campaigns, groups and ads read back saved fields; media and post creation return job handles with separate read-only polling tools. `verified=true` confirms saved configuration or successful processing, not impressions, ad approval or actual delivery.
- Writes are never retried automatically. `mutation_outcome=unknown` means inspect inventory before retrying. An acknowledged write with `verified=false` retains the resource ID so it can be inspected without duplicating the action.

## Read reports accurately

`reddit_get_report` accepts UTC timestamps in `YYYY-MM-DDTHH:00:00Z` form, with a range of at most 31 days. It defaults to campaign/day breakdowns, impressions, clicks, spend, CPC, CTR and separate click-/view-attributed signup and purchase counts. Other API reporting field names can be supplied through `fields`.

Inventory and reports return **one bounded page**. When `has_more=true`, call the same tool with the returned `next_url` and unchanged account, report dates, fields and breakdowns. Follow all pages before treating the report as complete. Each report page is a separate CSV. Pagination URLs are restricted to the original API resource; credentials are never placed in URLs.

Raw `spend` remains in microcurrency. `spend_currency_units` is converted using the account currency. CPC, CTR and other provider metrics remain unchanged. `metrics_updated_at` and account attribution windows accompany the results. Do not sum unique reach across pages or dimensions, or treat Reddit-attributed purchases as Lily's confirmed first payments; reconcile with first-party payment events.

## Validation boundary

Automated tests mock Reddit HTTP responses and exercise the real FastMCP interface, the complete paused-ad creation sequence, OAuth state validation, secret handling, pagination, ownership, currency conversion, pending jobs and interrupted writes. Request shapes are checked against the published v3 OpenAPI schema during implementation. Live read-only discovery validates authentication and accessible prerequisites; provider writes and actual delivery require separate verification on a reviewed campaign.


## Conversion tracking diagnostics

Use `reddit_get_pixel_health` with a pixel from `reddit_list_pixels`. It uses the existing management OAuth grant (`adsread`); a conversion-only access token cannot read pixel diagnostics. Null `sign_up` or `purchase` timestamps mean no such signal has been observed, not necessarily that an ad cohort should already have converted. Compare the timestamps with Lily's `capi_forward_result` events and its durable export ledger.

Lily's production server needs `REDDIT_CAPI_ACCESS_TOKEN` and `REDDIT_PIXEL_ID`, while its consent-aware browser integration needs `NEXT_PUBLIC_REDDIT_PIXEL_ID`. Saving the CAPI token in `~/.burnr8/.env` makes it available locally; deployment configuration is separate. Never paste credentials into MCP calls, reports or chat. CAPI test requests must put `test_id` inside `data`, alongside `events`; omit it for production. Burnr8 diagnostics do not generate synthetic production conversions.

For per-creative performance, request `reddit_get_report` with `breakdowns=["AD_ID"]`, follow all pages, and join ad destinations' `utm_content` to the first-party cohort. Keep click/view-attributed provider counts separate from confirmed first payments.

References: [Conversions API](https://ads-api.reddit.com/docs/v3/guides/programs/capi/direct-integration), [event verification](https://ads-api.reddit.com/docs/v3/guides/programs/capi/verify-events), [pixel diagnostics](https://ads-api.reddit.com/docs/v3/api/get-last-fired-at).
