"""Account-scoped Reddit media, ad posts, and paused ad creation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import requests
from fastmcp import FastMCP

from burnr8.reddit.client import RedditAdsApiError, get_reddit_client
from burnr8.reddit.creation import (
    bid_micros,
    linked_resource,
    list_data,
    media_url,
    profile_asset,
    profile_post,
    public_url,
    submit_job,
    targeting_values,
    text_field,
    utc_time,
)
from burnr8.reddit.errors import handle_reddit_errors
from burnr8.reddit.helpers import account_id as resolve_account_id
from burnr8.reddit.helpers import money_micros, object_data, owned_resource, require_usd, resource_id, write_and_verify
from burnr8.tools.reddit_ads import Account, Confirm, NextURL, PageSize, _list_page, _preview

ConversionGoal = Literal["PAGE_VISIT", "ADD_TO_CART", "PURCHASE", "LEAD", "SIGN_UP"]
Placement = Literal["FEED", "COMMENTS_PAGE"]
CallToAction = Literal["Learn More", "Sign Up", "Shop Now", "Download", "Subscribe", "Watch Now"]


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_reddit_errors
    def reddit_list_profiles(
        account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List the Reddit posting profiles linked to this ad account (maximum 100 per page)."""
        return _list_page(
            f"ad_accounts/{resolve_account_id(account_id)}/profiles", page_size=min(page_size, 100), next_url=next_url
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_pixels(
        account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List linked pixel IDs required for new ad groups. A listed pixel does not prove tracking is installed."""
        return _list_page(
            f"ad_accounts/{resolve_account_id(account_id)}/pixels", page_size=page_size, next_url=next_url
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_get_pixel_health(pixel_id: str, account_id: Account = None) -> dict[str, Any]:
        """Read last received conversion timestamps for an account-linked Reddit pixel.

        Uses Ads read credentials, not the conversion-only token. A received event
        proves signal ingestion, not campaign attribution or a confirmed payment.
        """
        selected = resolve_account_id(account_id)
        pixel = resource_id(pixel_id)
        client = get_reddit_client()
        linked_resource(client, selected, "pixels", pixel)
        result = client.request("GET", f"pixels/{pixel}/last_fired_at")
        data = result.get("data")
        if not isinstance(data, dict):
            raise ValueError("Reddit returned an invalid pixel health response.")
        return {
            "account_id": selected,
            "pixel_id": pixel,
            "checked_at": datetime.now(UTC).isoformat(),
            "last_fired_at": data,
            "interpretation": "Received events prove ingestion; use conversion reports and first-party payments to verify attribution.",
        }

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_creative_assets(
        profile_id: str, account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List a linked profile's stored creative assets, including processing status and hosted URLs."""
        linked_resource(get_reddit_client(), resolve_account_id(account_id), "profiles", profile_id)
        return _list_page(f"profiles/{resource_id(profile_id)}/creative_assets", page_size=page_size, next_url=next_url)

    @mcp.tool
    @handle_reddit_errors
    def reddit_list_ad_posts(
        profile_id: str, account_id: Account = None, page_size: PageSize = 100, next_url: NextURL = None
    ) -> dict[str, Any]:
        """List a linked profile's promoted structured posts to inspect creatives or reconcile interrupted creation."""
        linked_resource(get_reddit_client(), resolve_account_id(account_id), "profiles", profile_id)
        return _list_page(
            f"profiles/{resource_id(profile_id)}/structured_posts",
            page_size=min(page_size, 100),
            next_url=next_url,
            filters={"source": "PROMOTED"},
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_create_ad_group(
        name: str,
        campaign_id: str,
        daily_budget_dollars: float,
        conversion_pixel_id: str,
        geolocations: list[str],
        starts_at: str,
        ends_at: str,
        communities: list[str] | None = None,
        excluded_communities: list[str] | None = None,
        placements: list[Placement] | None = None,
        optimization_goal: ConversionGoal | None = None,
        bid_dollars: float | None = None,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Create a PAUSED manual ad group with explicit geography, pixel, daily budget and UTC start/end times.

        Supports standard non-CBO CLICKS, CONVERSIONS and IMPRESSIONS campaigns. Uses BIDLESS/CPC
        unless bid_dollars is provided for MANUAL_BIDDING. IMPRESSIONS requires a manual CPM bid ($3.50-$100).
        CONVERSIONS requires an explicit optimization_goal. Targeting expansion is off; placements default to FEED.
        Community names omit r/. Geolocations are Reddit IDs, e.g. US or CA:6167865. Preview is the default.
        """
        selected = resolve_account_id(account_id)
        name = text_field(name, "name")
        resource_id(campaign_id)
        resource_id(conversion_pixel_id)
        daily = money_micros(daily_budget_dollars, daily=True)
        start, end = utc_time(starts_at), utc_time(ends_at)
        if end <= start or end <= datetime.now(UTC):
            raise ValueError("ends_at must be after starts_at and in the future.")
        targeting: dict[str, Any] = {
            "geolocations": targeting_values(geolocations, "geolocations", r"[A-Za-z0-9:-]{1,100}", 20000),
            "locations": ["FEED"] if placements is None else placements,
            "expand_targeting": False,
        }
        targeting_values(targeting["locations"], "placements", r"FEED|COMMENTS_PAGE", 2)
        for key, values in (("communities", communities), ("excluded_communities", excluded_communities)):
            if values is not None:
                targeting[key] = targeting_values(values, key, r"[A-Za-z0-9_]{2,21}", 1000)
        if {v.lower() for v in communities or []} & {v.lower() for v in excluded_communities or []}:
            raise ValueError("A community cannot be both targeted and excluded.")
        client = get_reddit_client()
        require_usd(client, selected)
        campaign = owned_resource(client, "campaign", campaign_id, selected)
        if campaign.get("is_campaign_budget_optimization") is not False:
            raise ValueError("New ad groups require a campaign with ad-group budgeting (non-CBO).")
        if campaign.get("type") not in {None, "MANUAL"} or campaign.get("is_max") is True:
            raise ValueError("This tool creates ad groups in standard manual campaigns, not Reddit Max campaigns.")
        objective = campaign.get("objective")
        if objective not in {"CLICKS", "CONVERSIONS", "IMPRESSIONS"}:
            raise ValueError("This tool supports standard CLICKS, CONVERSIONS and IMPRESSIONS campaigns.")
        if objective == "CONVERSIONS":
            if optimization_goal not in {"PAGE_VISIT", "ADD_TO_CART", "PURCHASE", "LEAD", "SIGN_UP"}:
                raise ValueError("Choose an explicit supported optimization_goal for a CONVERSIONS campaign.")
        elif optimization_goal is not None:
            raise ValueError("optimization_goal is only accepted for CONVERSIONS campaigns.")
        bid_type = "CPM" if objective == "IMPRESSIONS" else "CPC"
        if bid_type == "CPM" and bid_dollars is None:
            raise ValueError("IMPRESSIONS campaigns require an explicit manual CPM bid_dollars.")
        changes: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "configured_status": "PAUSED",
            "goal_type": "DAILY_SPEND",
            "goal_value": daily,
            "bid_strategy": "BIDLESS" if bid_dollars is None else "MANUAL_BIDDING",
            "bid_type": bid_type,
            "conversion_pixel_id": conversion_pixel_id,
            "start_time": starts_at,
            "end_time": ends_at,
            "targeting": targeting,
        }
        if bid_dollars is not None:
            changes["bid_value"] = bid_micros(bid_dollars, bid_type)
        if optimization_goal is not None:
            changes["optimization_goal"] = optimization_goal
        linked_resource(client, selected, "pixels", conversion_pixel_id)
        plan = {"operation": "create_ad_group", "campaign_id": campaign_id, "request": {"data": changes}}
        if not confirm:
            return _preview(selected, plan)
        return write_and_verify(
            client,
            method="POST",
            path=f"ad_accounts/{selected}/ad_groups",
            kind="ad_group",
            selected=selected,
            changes=changes,
        )

    @mcp.tool
    @handle_reddit_errors
    def reddit_upload_media(
        profile_id: str,
        name: str,
        media_type: Literal["IMAGE", "VIDEO"],
        media_url: str,
        poster_url: str | None = None,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Import one image/video from a public HTTPS URL into a linked profile's Reddit asset library.

        Reddit downloads the URL; local paths/base64 are not supported. VIDEO requires an image poster_url.
        Defaults to preview. On submission retain upload_id and poll reddit_get_media_upload; never resubmit to poll.
        """
        selected = resolve_account_id(account_id)
        resource_id(profile_id)
        if media_type not in {"IMAGE", "VIDEO"}:
            raise ValueError("media_type must be IMAGE or VIDEO.")
        if (media_type == "VIDEO") != (poster_url is not None):
            raise ValueError("poster_url is required for VIDEO and must be omitted for IMAGE.")
        data: dict[str, Any] = {
            "name": text_field(name, "name"),
            "type": media_type,
            "media": {"type": "URL", "url": public_url(media_url)},
            "reference_id": str(uuid4()),
        }
        if poster_url is not None:
            data["poster"] = {"type": "URL", "url": public_url(poster_url)}
        client = get_reddit_client()
        linked_resource(client, selected, "profiles", profile_id)
        if not confirm:
            return _preview(
                selected, {"operation": "upload_media", "profile_id": profile_id, "request": {"data": [data]}}
            )
        response = submit_job(client, f"profiles/{profile_id}/creative_assets/uploads", [data])
        result: dict[str, Any] = {
            "account_id": selected,
            "profile_id": profile_id,
            "reference_id": data["reference_id"],
        }
        if response.get("error"):
            return {**result, **response}
        rows = response.get("data")
        upload_id = (
            rows[0].get("id") if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else None
        )
        if not isinstance(upload_id, str) or not upload_id:
            return {
                **result,
                "submitted": True,
                "verified": False,
                "warning": True,
                "message": "Upload acknowledged without a usable upload ID. Inspect creative assets before retrying.",
            }
        return {
            **result,
            "submitted": True,
            "verified": False,
            "upload_id": upload_id,
            "next_tool": "reddit_get_media_upload",
            "message": "Upload accepted; processing is not yet verified.",
        }

    @mcp.tool
    @handle_reddit_errors
    def reddit_get_media_upload(profile_id: str, upload_id: str, account_id: Account = None) -> dict[str, Any]:
        """Poll one upload within a linked profile. ACTIVE plus an ACTIVE result means the media is usable."""
        selected = resolve_account_id(account_id)
        resource_id(upload_id)
        client = get_reddit_client()
        linked_resource(client, selected, "profiles", profile_id)
        rows = list_data(
            client.request("GET", f"profiles/{profile_id}/creative_assets/uploads", params={"id": upload_id})
        )
        upload = next((row for row in rows if row.get("id") == upload_id), None)
        if upload is None:
            raise ValueError("The upload was not found in the selected profile.")
        status = upload.get("status")
        asset = upload.get("result")
        ready = (
            status == "ACTIVE" and isinstance(asset, dict) and asset.get("status") == "ACTIVE" and bool(asset.get("id"))
        )
        result: dict[str, Any] = {
            "account_id": selected,
            "profile_id": profile_id,
            "upload_id": upload_id,
            "status": status,
            "ready": ready,
            "verified": ready,
        }
        if ready:
            result["asset"] = asset
        elif status == "PROCESSING_MEDIA":
            result.update(pending=True, message="Media is processing. Poll this upload ID again; do not re-upload.")
        else:
            result.update(warning=True, message="Media is not usable. Inspect this upload in Reddit before proceeding.")
        return result

    @mcp.tool
    @handle_reddit_errors
    def reddit_create_ad_post(
        profile_id: str,
        headline: str,
        destination_url: str,
        media_asset_id: str,
        call_to_action: CallToAction = "Learn More",
        thumbnail_asset_id: str | None = None,
        allow_comments: bool = False,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Create an image/video ad post from an ACTIVE asset belonging to this linked profile.

        The post can have a Reddit URL before any ad runs; this is not a private draft. No community is selected.
        Video uses its uploaded poster unless an IMAGE thumbnail_asset_id is supplied. Comments default off.
        Keep UTM parameters in destination_url. Retain the job_id and poll reddit_get_ad_post_job to obtain post_id.
        """
        selected = resolve_account_id(account_id)
        headline = text_field(headline, "headline", 300)
        destination_url = public_url(destination_url)
        if call_to_action not in {"Learn More", "Sign Up", "Shop Now", "Download", "Subscribe", "Watch Now"}:
            raise ValueError("Choose a supported call_to_action.")
        resource_id(media_asset_id)
        if thumbnail_asset_id is not None:
            resource_id(thumbnail_asset_id)
        client = get_reddit_client()
        linked_resource(client, selected, "profiles", profile_id)
        asset = profile_asset(client, profile_id, media_asset_id)
        kind = asset["type"]
        creative: dict[str, Any] = {
            "type": kind,
            "headline": headline,
            "destination": {"type": "URL", "url": destination_url, "call_to_action": call_to_action},
            kind.lower(): {"media": media_url(asset)},
            "enhancements": {"user_generated_content": {"enroll_status": "OPT_OUT"}},
        }
        if thumbnail_asset_id is not None:
            thumbnail = profile_asset(client, profile_id, thumbnail_asset_id)
            if thumbnail["type"] != "IMAGE":
                raise ValueError("thumbnail_asset_id must reference an ACTIVE IMAGE asset.")
            creative["thumbnail"] = {"media": media_url(thumbnail)}
        elif kind == "VIDEO":
            creative["thumbnail"] = {"media": media_url(asset, "poster")}
        data = {"allow_comments": allow_comments, "creative": creative}
        if not confirm:
            return _preview(
                selected, {"operation": "create_ad_post", "profile_id": profile_id, "request": {"data": data}}
            )
        response = submit_job(client, f"profiles/{profile_id}/structured_posts/jobs", data)
        result: dict[str, Any] = {"account_id": selected, "profile_id": profile_id}
        if response.get("error"):
            return {**result, **response}
        job = response.get("data")
        job_id = job.get("id") if isinstance(job, dict) else None
        if not isinstance(job_id, str) or not job_id:
            return {
                **result,
                "submitted": True,
                "verified": False,
                "warning": True,
                "message": "Post job acknowledged without a usable job ID. Inspect ad posts before retrying.",
            }
        return {
            **result,
            "submitted": True,
            "verified": False,
            "job_id": job_id,
            "next_tool": "reddit_get_ad_post_job",
            "message": "Post creation accepted; poll the job to verify completion.",
        }

    @mcp.tool
    @handle_reddit_errors
    def reddit_get_ad_post_job(profile_id: str, job_id: str, account_id: Account = None) -> dict[str, Any]:
        """Poll a structured ad-post job; on SUCCESS read back the post and verify its profile before returning it."""
        selected = resolve_account_id(account_id)
        resource_id(job_id)
        client = get_reddit_client()
        linked_resource(client, selected, "profiles", profile_id)
        job = object_data(client.request("GET", f"structured_posts/jobs/{job_id}"))
        if job.get("id") != job_id:
            raise ValueError("Reddit returned a different post job.")
        status = job.get("status")
        result: dict[str, Any] = {
            "account_id": selected,
            "profile_id": profile_id,
            "job_id": job_id,
            "status": status,
            "ready": False,
            "verified": False,
        }
        if status == "SUCCESS" and isinstance(job.get("post_id"), str):
            try:
                post = profile_post(client, profile_id, job["post_id"])
            except (requests.RequestException, RedditAdsApiError):
                return {
                    **result,
                    "post_id": job["post_id"],
                    "warning": True,
                    "message": "Job succeeded; post read-back failed. Poll this same job again before creating an ad.",
                }
            result.update(ready=True, verified=True, post_id=post["id"], post=post)
        elif status in {"PROCESSING", "QUEUED"}:
            result.update(
                pending=True, message="Post creation is pending. Poll this job again; do not create another post."
            )
        else:
            result.update(
                warning=True, message="Post creation is not verified. Inspect this job and ad posts before retrying."
            )
        return result

    @mcp.tool
    @handle_reddit_errors
    def reddit_create_ad(
        name: str,
        ad_group_id: str,
        profile_id: str,
        post_id: str,
        preview_expires_at: str | None = None,
        account_id: Account = None,
        confirm: Confirm = False,
    ) -> dict[str, Any]:
        """Create and read back a PAUSED image/video ad from a verified profile post and an owned manual ad group.

        The click URL is copied from the post destination, preserving its UTMs. A placement preview link is
        requested for seven days by default, or until preview_expires_at (UTC YYYY-MM-DDTHH:MM:SSZ, within 30 days).
        Creation never activates the ad, ad group or campaign. Preview by default; confirm=true performs the write.
        """
        selected = resolve_account_id(account_id)
        name = text_field(name, "name")
        resource_id(ad_group_id)
        resource_id(profile_id)
        resource_id(post_id)
        now = datetime.now(UTC)
        expiry = utc_time(preview_expires_at) if preview_expires_at is not None else now + timedelta(days=7)
        if not now < expiry <= now + timedelta(days=30):
            raise ValueError("preview_expires_at must be in the future and within the next 30 days.")
        client = get_reddit_client()
        group = owned_resource(client, "ad_group", ad_group_id, selected)
        campaign = owned_resource(client, "campaign", str(group.get("campaign_id", "")), selected)
        # Live legacy groups omit type. Their parent campaign still identifies itself as MANUAL.
        if (
            group.get("type") not in {None, "MANUAL"}
            or campaign.get("type") not in {None, "MANUAL"}
            or campaign.get("is_max") is True
            or (group.get("type") is None and campaign.get("type") != "MANUAL")
        ):
            raise ValueError("This tool creates standard ads in MANUAL ad groups.")
        linked_resource(client, selected, "profiles", profile_id)
        post = profile_post(client, profile_id, post_id)
        creative = post.get("creative")
        if not isinstance(creative, dict) or creative.get("type") not in {"IMAGE", "VIDEO"}:
            raise ValueError("This tool creates image or video ads from structured posts.")
        destination = creative.get("destination")
        if not isinstance(destination, dict) or not isinstance(destination.get("url"), str):
            raise ValueError("The ad post has no usable destination URL.")
        changes = {
            "name": name,
            "ad_group_id": ad_group_id,
            "profile_id": profile_id,
            "post_id": post_id,
            "configured_status": "PAUSED",
            "click_url": public_url(destination["url"]),
            "preview_expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if not confirm:
            return _preview(selected, {"operation": "create_ad", "request": {"data": changes}, "post": post})
        result = write_and_verify(
            client,
            method="POST",
            path=f"ad_accounts/{selected}/ads",
            kind="ad",
            selected=selected,
            changes=changes,
        )
        if result.get("created"):
            saved = result.get("resource", {})
            result["preview_url"] = saved.get("preview_url")
            result["post_url"] = saved.get("post_url") or post.get("url")
            if not result["preview_url"]:
                result["warning"] = True
                result.setdefault(
                    "message",
                    "Ad created paused; Reddit has not returned a placement preview link. Review the post URL and "
                    "generate a test URL in Ads Manager if needed before activation.",
                )
        return result
