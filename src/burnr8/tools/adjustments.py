from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

if TYPE_CHECKING:
    from fastmcp import FastMCP

from burnr8.client import get_client
from burnr8.errors import handle_google_ads_errors
from burnr8.helpers import build_mutate_request, require_customer_id, run_gaql, validate_bid_modifier, validate_id

VALID_DEVICE_TYPES = {"MOBILE", "DESKTOP", "TABLET"}
VALID_PRESENCE_TYPES = {"PRESENCE", "PRESENCE_OR_INTEREST", "SEARCH_INTEREST"}
VALID_DAYS_OF_WEEK = {
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
}


def register(mcp: FastMCP) -> None:
    @mcp.tool
    @handle_google_ads_errors
    def pause_keyword(
        ad_group_id: Annotated[str, Field(description="Ad group ID containing the keyword")],
        criterion_id: Annotated[str, Field(description="Keyword criterion ID to pause")],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Pause a specific keyword by criterion ID."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(ad_group_id, "ad_group_id"):
            return {"error": True, "message": err}
        if err := validate_id(criterion_id, "criterion_id"):
            return {"error": True, "message": err}

        client = get_client()
        ad_group_criterion_service = client.get_service("AdGroupCriterionService")

        operation = client.get_type("AdGroupCriterionOperation")
        criterion = operation.update
        criterion.resource_name = ad_group_criterion_service.ad_group_criterion_path(
            customer_id, ad_group_id, criterion_id
        )
        criterion.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
        operation.update_mask.paths.append("status")

        response = ad_group_criterion_service.mutate_ad_group_criteria(
            request=build_mutate_request(client, "MutateAdGroupCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": f"Validation succeeded. This will pause keyword '{criterion_id}'. Set confirm=true to execute."}

        return {
            "resource_name": response.results[0].resource_name,
            "new_status": "PAUSED",
        }

    @mcp.tool
    @handle_google_ads_errors
    def set_device_bid_adjustment(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        device_type: Annotated[str, Field(description="Device type: MOBILE, DESKTOP, or TABLET")],
        bid_modifier: Annotated[
            float, Field(description="Bid modifier (0.0 = exclude device, 1.0 = no change, 1.5 = +50%, 0.7 = -30%)")
        ],
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Set a bid adjustment for a device type on a campaign. Creates the device criterion if it doesn't exist (common with Smart Bidding strategies)."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if device_type.upper() not in VALID_DEVICE_TYPES:
            return {
                "error": True,
                "message": f"Invalid device_type '{device_type}'. Must be one of: {', '.join(sorted(VALID_DEVICE_TYPES))}",
            }
        if err := validate_bid_modifier(bid_modifier):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")

        device_enum_map = {
            "MOBILE": client.enums.DeviceEnum.MOBILE,
            "DESKTOP": client.enums.DeviceEnum.DESKTOP,
            "TABLET": client.enums.DeviceEnum.TABLET,
        }

        # Query for existing device criteria
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.device.type,
                campaign_criterion.bid_modifier
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
                AND campaign_criterion.type = 'DEVICE'
        """
        rows = run_gaql(client, customer_id, query)

        # Find the criterion for the requested device type
        target_criterion_id = None
        for row in rows:
            cc = row.get("campaign_criterion", {})
            device = cc.get("device", {})
            if device.get("type") == device_type.upper():
                target_criterion_id = cc.get("criterion_id")
                break

        operation = client.get_type("CampaignCriterionOperation")

        if target_criterion_id is not None:
            # Update existing criterion
            criterion = operation.update
            criterion.resource_name = campaign_criterion_service.campaign_criterion_path(
                customer_id, campaign_id, target_criterion_id
            )
            criterion.bid_modifier = bid_modifier
            operation.update_mask.paths.append("bid_modifier")
            action = "updated"
        else:
            # Create new device criterion (needed for Smart Bidding campaigns)
            criterion = operation.create
            criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
            criterion.device.type_ = device_enum_map[device_type.upper()]
            criterion.bid_modifier = bid_modifier
            action = "created"

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": "Validation succeeded. This will set device bid adjustment. Set confirm=true to execute."}

        return {
            "resource_name": response.results[0].resource_name,
            "device_type": device_type.upper(),
            "bid_modifier": bid_modifier,
            "action": action,
        }

    @mcp.tool
    @handle_google_ads_errors
    def list_device_bid_adjustments(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List current device bid adjustments for a campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.device.type,
                campaign_criterion.bid_modifier,
                campaign.id,
                campaign.name
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
                AND campaign_criterion.type = 'DEVICE'
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            cc = row.get("campaign_criterion", {})
            device = cc.get("device", {})
            c = row.get("campaign", {})
            results.append(
                {
                    "criterion_id": cc.get("criterion_id"),
                    "device_type": device.get("type"),
                    "bid_modifier": cc.get("bid_modifier"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def set_ad_schedule(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        day_of_week: Annotated[
            str, Field(description="Day of week: MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY")
        ],
        start_hour: Annotated[int, Field(description="Start hour (0-23)")],
        end_hour: Annotated[
            int, Field(description="End hour (0-24, use 24 for end of day/midnight. Must be greater than start_hour)")
        ],
        bid_modifier: Annotated[float, Field(description="Bid modifier (1.0 = no change, 1.5 = +50%)")] = 1.0,
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Set an ad schedule (dayparting) for a campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if day_of_week.upper() not in VALID_DAYS_OF_WEEK:
            return {
                "error": True,
                "message": f"Invalid day_of_week '{day_of_week}'. Must be one of: {', '.join(sorted(VALID_DAYS_OF_WEEK))}",
            }
        if not (0 <= start_hour <= 23):
            return {"error": True, "message": f"start_hour must be 0-23, got {start_hour}"}
        if not (0 <= end_hour <= 24):
            return {"error": True, "message": f"end_hour must be 0-24, got {end_hour}"}
        if end_hour <= start_hour:
            return {"error": True, "message": f"end_hour ({end_hour}) must be greater than start_hour ({start_hour})"}
        if err := validate_bid_modifier(bid_modifier):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")

        day_map = {
            "MONDAY": client.enums.DayOfWeekEnum.MONDAY,
            "TUESDAY": client.enums.DayOfWeekEnum.TUESDAY,
            "WEDNESDAY": client.enums.DayOfWeekEnum.WEDNESDAY,
            "THURSDAY": client.enums.DayOfWeekEnum.THURSDAY,
            "FRIDAY": client.enums.DayOfWeekEnum.FRIDAY,
            "SATURDAY": client.enums.DayOfWeekEnum.SATURDAY,
            "SUNDAY": client.enums.DayOfWeekEnum.SUNDAY,
        }

        operation = client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.ad_schedule.day_of_week = day_map[day_of_week.upper()]
        criterion.ad_schedule.start_hour = start_hour
        criterion.ad_schedule.end_hour = end_hour
        criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
        criterion.bid_modifier = bid_modifier

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": "Validation succeeded. This will set ad schedule. Set confirm=true to execute."}

        resource_name = response.results[0].resource_name
        return {
            "resource_name": resource_name,
            "day_of_week": day_of_week.upper(),
            "start_hour": start_hour,
            "end_hour": end_hour,
            "bid_modifier": bid_modifier,
        }

    @mcp.tool
    @handle_google_ads_errors
    def list_ad_schedules(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List current ad schedules (dayparting) for a campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.ad_schedule.day_of_week,
                campaign_criterion.ad_schedule.start_hour,
                campaign_criterion.ad_schedule.end_hour,
                campaign_criterion.ad_schedule.start_minute,
                campaign_criterion.ad_schedule.end_minute,
                campaign_criterion.bid_modifier,
                campaign.id,
                campaign.name
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
                AND campaign_criterion.type = 'AD_SCHEDULE'
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            cc = row.get("campaign_criterion", {})
            schedule = cc.get("ad_schedule", {})
            c = row.get("campaign", {})
            results.append(
                {
                    "criterion_id": cc.get("criterion_id"),
                    "day_of_week": schedule.get("day_of_week"),
                    "start_hour": schedule.get("start_hour"),
                    "end_hour": schedule.get("end_hour"),
                    "start_minute": schedule.get("start_minute"),
                    "end_minute": schedule.get("end_minute"),
                    "bid_modifier": cc.get("bid_modifier"),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def remove_ad_schedule(
        campaign_id: Annotated[str, Field(description="Campaign ID containing the ad schedule")],
        criterion_id: Annotated[str, Field(description="Ad schedule criterion ID to remove")],
        confirm: Annotated[bool, Field(description="Must be true to execute removal.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Remove an ad schedule criterion from a campaign. Requires confirm=true."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if err := validate_id(criterion_id, "criterion_id"):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")

        resource_name = campaign_criterion_service.campaign_criterion_path(customer_id, campaign_id, criterion_id)
        operation = client.get_type("CampaignCriterionOperation")
        operation.remove = resource_name

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "message": f"Validation succeeded. This will remove ad schedule criterion {criterion_id} from campaign {campaign_id}. "
                "Set confirm=true to execute.",
            }

        return {"removed": response.results[0].resource_name}

    @mcp.tool
    @handle_google_ads_errors
    def list_location_targets(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> list[dict] | dict:
        """List location targets (geo targets) for a campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        query = f"""
            SELECT
                campaign_criterion.criterion_id,
                campaign_criterion.location.geo_target_constant,
                campaign_criterion.bid_modifier,
                campaign_criterion.negative,
                campaign.id,
                campaign.name
            FROM campaign_criterion
            WHERE campaign.id = {campaign_id}
                AND campaign_criterion.type = 'LOCATION'
        """
        rows = run_gaql(client, customer_id, query)
        results = []
        for row in rows:
            cc = row.get("campaign_criterion", {})
            loc = cc.get("location", {})
            c = row.get("campaign", {})
            results.append(
                {
                    "criterion_id": cc.get("criterion_id"),
                    "geo_target_constant": loc.get("geo_target_constant"),
                    "bid_modifier": cc.get("bid_modifier"),
                    "negative": cc.get("negative", False),
                    "campaign_id": c.get("id"),
                    "campaign_name": c.get("name"),
                }
            )
        return results

    @mcp.tool
    @handle_google_ads_errors
    def add_location_target(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        geo_target_id: Annotated[
            str,
            Field(
                description="Geo target constant ID (e.g. 2840=US, 2826=UK, 2124=Canada, 1014044=New York City). Find IDs at developers.google.com/google-ads/api/data/geotargets"
            ),
        ],
        bid_modifier: Annotated[
            float, Field(description="Bid modifier for this location (1.0 = no change, 1.2 = +20%)")
        ] = 1.0,
        negative: Annotated[
            bool, Field(description="Set to true to EXCLUDE this location instead of targeting it")
        ] = False,
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Add a location target (or exclusion) to a campaign."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if err := validate_id(geo_target_id, "geo_target_id"):
            return {"error": True, "message": err}
        if not negative and (err := validate_bid_modifier(bid_modifier)):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        campaign_service = client.get_service("CampaignService")

        operation = client.get_type("CampaignCriterionOperation")
        criterion = operation.create
        criterion.campaign = campaign_service.campaign_path(customer_id, campaign_id)
        criterion.location.geo_target_constant = f"geoTargetConstants/{geo_target_id}"
        criterion.negative = negative
        if not negative:
            criterion.bid_modifier = bid_modifier

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": "Validation succeeded. This will add location target. Set confirm=true to execute."}

        return {
            "resource_name": response.results[0].resource_name,
            "geo_target_id": geo_target_id,
            "negative": negative,
            "bid_modifier": bid_modifier if not negative else None,
        }

    @mcp.tool
    @handle_google_ads_errors
    def remove_location_target(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        criterion_id: Annotated[str, Field(description="Location criterion ID to remove")],
        confirm: Annotated[bool, Field(description="Must be true to execute removal.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Remove a location target from a campaign. Requires confirm=true."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if err := validate_id(criterion_id, "criterion_id"):
            return {"error": True, "message": err}

        client = get_client()
        campaign_criterion_service = client.get_service("CampaignCriterionService")
        resource_name = campaign_criterion_service.campaign_criterion_path(customer_id, campaign_id, criterion_id)
        operation = client.get_type("CampaignCriterionOperation")
        operation.remove = resource_name

        response = campaign_criterion_service.mutate_campaign_criteria(
            request=build_mutate_request(client, "MutateCampaignCriteriaRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {
                "warning": True,
                "validated": True,
                "message": f"Validation succeeded. This will remove location criterion {criterion_id} from campaign {campaign_id}. "
                "Set confirm=true to execute.",
            }

        return {"removed": response.results[0].resource_name}

    @mcp.tool
    @handle_google_ads_errors
    def get_geo_target_type_setting(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Get the location targeting presence setting for a campaign (Presence vs Presence or Interest)."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}

        client = get_client()
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.geo_target_type_setting.positive_geo_target_type,
                campaign.geo_target_type_setting.negative_geo_target_type
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        rows = run_gaql(client, customer_id, query)
        if rows:
            c = rows[0].get("campaign", {})
            gts = c.get("geo_target_type_setting", {})
            return {
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "positive_geo_target_type": gts.get("positive_geo_target_type"),
                "negative_geo_target_type": gts.get("negative_geo_target_type"),
            }
        return {"error": True, "message": "Campaign not found"}

    @mcp.tool
    @handle_google_ads_errors
    def set_geo_target_type_setting(
        campaign_id: Annotated[str, Field(description="Campaign ID")],
        positive_type: Annotated[
            str,
            Field(
                description="Who sees your ads: PRESENCE (people IN the location — recommended), PRESENCE_OR_INTEREST (people in or interested in the location), SEARCH_INTEREST (people searching for the location)"
            ),
        ] = "PRESENCE",
        negative_type: Annotated[
            str, Field(description="Who is excluded: PRESENCE (people IN excluded locations) or PRESENCE_OR_INTEREST")
        ] = "PRESENCE",
        confirm: Annotated[bool, Field(description="Must be true to execute.")] = False,
        customer_id: Annotated[
            str | None, Field(description="Google Ads customer ID (no dashes). Uses active account if not provided.")
        ] = None,
    ) -> dict:
        """Set the location targeting presence mode for a campaign. PRESENCE is recommended — it targets people physically in your locations, not just searching about them."""
        customer_id, cid_err = require_customer_id(customer_id)
        if cid_err:
            return cid_err
        if err := validate_id(campaign_id, "campaign_id"):
            return {"error": True, "message": err}
        if positive_type.upper() not in VALID_PRESENCE_TYPES:
            return {
                "error": True,
                "message": f"Invalid positive_type '{positive_type}'. Must be one of: {', '.join(sorted(VALID_PRESENCE_TYPES))}",
            }
        neg_valid = {"PRESENCE", "PRESENCE_OR_INTEREST"}
        if negative_type.upper() not in neg_valid:
            return {
                "error": True,
                "message": f"Invalid negative_type '{negative_type}'. Must be one of: {', '.join(sorted(neg_valid))}",
            }

        client = get_client()
        campaign_service = client.get_service("CampaignService")

        positive_map = {
            "PRESENCE": client.enums.PositiveGeoTargetTypeEnum.PRESENCE,
            "PRESENCE_OR_INTEREST": client.enums.PositiveGeoTargetTypeEnum.PRESENCE_OR_INTEREST,
            "SEARCH_INTEREST": client.enums.PositiveGeoTargetTypeEnum.SEARCH_INTEREST,
        }
        negative_map = {
            "PRESENCE": client.enums.NegativeGeoTargetTypeEnum.PRESENCE,
            "PRESENCE_OR_INTEREST": client.enums.NegativeGeoTargetTypeEnum.PRESENCE_OR_INTEREST,
        }

        operation = client.get_type("CampaignOperation")
        campaign = operation.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
        campaign.geo_target_type_setting.positive_geo_target_type = positive_map[positive_type.upper()]
        campaign.geo_target_type_setting.negative_geo_target_type = negative_map[negative_type.upper()]
        operation.update_mask.paths.extend(
            [
                "geo_target_type_setting.positive_geo_target_type",
                "geo_target_type_setting.negative_geo_target_type",
            ]
        )

        response = campaign_service.mutate_campaigns(
            request=build_mutate_request(client, "MutateCampaignsRequest", customer_id, [operation], validate_only=not confirm)
        )
        if not confirm:
            return {"warning": True, "validated": True, "message": "Validation succeeded. This will set geo target type setting. Set confirm=true to execute."}

        return {
            "resource_name": response.results[0].resource_name,
            "positive_geo_target_type": positive_type.upper(),
            "negative_geo_target_type": negative_type.upper(),
        }
