from dotenv import load_dotenv

load_dotenv()

from fastmcp import FastMCP
from burnr8 import __version__
from burnr8.tools import register_all_tools

mcp = FastMCP(name="burnr8", version=__version__)
register_all_tools(mcp)


# ── Resources ──────────────────────────────────────────────────────────────────


@mcp.resource("burnr8://usage")
def usage_resource() -> str:
    """Current API usage stats — ops today, errors, rate limit status."""
    from burnr8.logging import get_usage_stats
    import json

    return json.dumps(get_usage_stats(), indent=2)


@mcp.resource("burnr8://accounts")
def accounts_resource() -> str:
    """List of accessible Google Ads accounts."""
    from burnr8.client import get_client
    import json

    try:
        client = get_client()
        svc = client.get_service("CustomerService")
        resp = svc.list_accessible_customers()
        accounts = [{"customer_id": r.split("/")[-1]} for r in resp.resource_names]
        return json.dumps(accounts, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Resource Templates ─────────────────────────────────────────────────────────


@mcp.resource("burnr8://accounts/{customer_id}/performance")
def account_performance(customer_id: str) -> str:
    """Campaign performance summary for the last 30 days — loaded as context automatically."""
    from burnr8.client import get_client
    from burnr8.helpers import run_gaql
    import json

    try:
        client = get_client()
        rows = run_gaql(
            client,
            customer_id,
            """
            SELECT
                campaign.id, campaign.name, campaign.status,
                metrics.impressions, metrics.clicks, metrics.cost_micros,
                metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE campaign.status != 'REMOVED'
                AND segments.date DURING LAST_30_DAYS
            ORDER BY metrics.cost_micros DESC
        """,
        )
        campaigns = []
        total_spend = 0
        total_conversions = 0
        for row in rows:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = int(m.get("cost_micros", 0)) / 1_000_000
            conv = float(m.get("conversions", 0))
            total_spend += cost
            total_conversions += conv
            campaigns.append(
                {
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "spend": round(cost, 2),
                    "clicks": int(m.get("clicks", 0)),
                    "impressions": int(m.get("impressions", 0)),
                    "conversions": round(conv, 1),
                }
            )
        return json.dumps(
            {
                "customer_id": customer_id,
                "period": "LAST_30_DAYS",
                "total_spend": round(total_spend, 2),
                "total_conversions": round(total_conversions, 1),
                "avg_cpa": round(total_spend / total_conversions, 2)
                if total_conversions > 0
                else None,
                "campaigns": campaigns,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("burnr8://accounts/{customer_id}/keywords")
def account_keywords(customer_id: str) -> str:
    """Keyword health summary — quality scores, top performers, underperformers."""
    from burnr8.client import get_client
    from burnr8.helpers import run_gaql
    import json

    try:
        client = get_client()
        rows = run_gaql(
            client,
            customer_id,
            """
            SELECT
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                ad_group_criterion.quality_info.quality_score,
                ad_group_criterion.status,
                campaign.name,
                metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
            FROM keyword_view
            WHERE segments.date DURING LAST_30_DAYS
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """,
        )
        keywords = []
        quality_scores = []
        for row in rows:
            cr = row.get("ad_group_criterion", {})
            kw = cr.get("keyword", {})
            qs = cr.get("quality_info", {}).get("quality_score")
            m = row.get("metrics", {})
            c = row.get("campaign", {})
            if qs is not None and int(qs) > 0:
                quality_scores.append(int(qs))
            keywords.append(
                {
                    "keyword": kw.get("text"),
                    "match_type": kw.get("match_type"),
                    "quality_score": qs,
                    "status": cr.get("status"),
                    "campaign": c.get("name"),
                    "spend": round(int(m.get("cost_micros", 0)) / 1_000_000, 2),
                    "clicks": int(m.get("clicks", 0)),
                    "conversions": float(m.get("conversions", 0)),
                }
            )
        avg_qs = (
            round(sum(quality_scores) / len(quality_scores), 1)
            if quality_scores
            else None
        )
        low_qs = [
            k
            for k in keywords
            if k["quality_score"] is not None and int(k["quality_score"]) < 5
        ]
        return json.dumps(
            {
                "customer_id": customer_id,
                "period": "LAST_30_DAYS",
                "avg_quality_score": avg_qs,
                "low_quality_count": len(low_qs),
                "top_keywords": keywords[:10],
                "low_quality_keywords": low_qs[:10],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("burnr8://accounts/{customer_id}/structure")
def account_structure(customer_id: str) -> str:
    """Account structure — campaigns, ad groups, keyword counts, budget info."""
    from burnr8.client import get_client
    from burnr8.helpers import run_gaql
    import json

    try:
        client = get_client()
        # Campaign + budget info
        campaigns = run_gaql(
            client,
            customer_id,
            """
            SELECT
                campaign.id, campaign.name, campaign.status,
                campaign.advertising_channel_type, campaign.bidding_strategy_type,
                campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            ORDER BY campaign.name
        """,
        )
        # Ad group counts per campaign
        ad_groups = run_gaql(
            client,
            customer_id,
            """
            SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status
            FROM ad_group
            WHERE ad_group.status != 'REMOVED'
        """,
        )
        structure = []
        for row in campaigns:
            c = row.get("campaign", {})
            b = row.get("campaign_budget", {})
            cid = c.get("id")
            ag_count = sum(
                1 for ag in ad_groups if ag.get("campaign", {}).get("id") == cid
            )
            structure.append(
                {
                    "campaign_id": cid,
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "channel_type": c.get("advertising_channel_type"),
                    "bidding_strategy": c.get("bidding_strategy_type"),
                    "daily_budget": round(
                        int(b.get("amount_micros", 0)) / 1_000_000, 2
                    ),
                    "ad_group_count": ag_count,
                }
            )
        return json.dumps(
            {
                "customer_id": customer_id,
                "campaign_count": len(structure),
                "campaigns": structure,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Prompts ────────────────────────────────────────────────────────────────────


@mcp.prompt
def audit(customer_id: str) -> str:
    """Run a complete Google Ads account audit."""
    return f"""Run a full audit of Google Ads account {customer_id}:

1. Call quick_audit to get the full account snapshot
2. Identify wasted spend (keywords with spend but 0 conversions)
3. Check quality scores (flag anything below 5)
4. Review ad strength (flag anything below GOOD)
5. Check conversion tracking setup (are primary conversions set correctly?)
6. Check negative keyword coverage
7. Summarize findings with a health score and prioritized action items"""


@mcp.prompt
def optimize(customer_id: str) -> str:
    """Find and fix wasted ad spend."""
    return f"""Optimize Google Ads account {customer_id} for wasted spend:

1. Call cleanup_wasted_spend to identify non-converting keywords
2. Review search terms report for irrelevant queries
3. Recommend specific negative keywords to add (use Exact match for specific terms, Phrase match for patterns)
4. Identify keywords to pause (high spend, zero conversions, low quality score)
5. Present total estimated monthly savings"""


@mcp.prompt
def new_campaign(customer_id: str, product: str, url: str) -> str:
    """Plan and launch a new search campaign."""
    return f"""Create a new Google Ads search campaign for account {customer_id}:

Product/service: {product}
Landing page: {url}

Steps:
1. Research keywords related to the product using research_keywords
2. Recommend campaign structure (ad groups, keyword themes)
3. Write RSA headlines (15) and descriptions (4) following Google Ads best practices
4. Use launch_campaign to create everything in one step
5. Confirm the campaign was created PAUSED and review the setup"""


if __name__ == "__main__":
    mcp.run()
