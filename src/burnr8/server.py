from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

# Load credentials: ~/.burnr8/.env is the canonical location (written by burnr8-setup).
# override=True so credentials saved by the wizard always win over stale shell exports.
# CWD .env is the fallback for clone-and-install workflow (no override — lowest priority).
_burnr8_env = Path.home() / ".burnr8" / ".env"
if _burnr8_env.exists():
    load_dotenv(_burnr8_env, override=True)
load_dotenv()  # CWD .env — won't override anything already set

from fastmcp import FastMCP  # noqa: E402

from burnr8 import __version__  # noqa: E402
from burnr8.tools import register_all_tools  # noqa: E402

mcp = FastMCP(name="burnr8", version=__version__)
register_all_tools(mcp)


# ── Resources ──────────────────────────────────────────────────────────────────


@mcp.resource("burnr8://usage")
def usage_resource() -> str:
    """Current API usage stats — ops today, errors, rate limit status."""
    import json

    from burnr8.logging import get_usage_stats

    try:
        stats = get_usage_stats()
        return json.dumps(stats, indent=2)
    except Exception as e:
        msg = str(e)[:200] if str(e) else "Unknown error"
        return json.dumps({"error": msg})


@mcp.resource("burnr8://accounts")
def accounts_resource() -> str:
    """List of accessible Google Ads accounts."""
    import json

    from burnr8.client import get_client

    try:
        client = get_client()
        svc = client.get_service("CustomerService")
        resp = svc.list_accessible_customers()
        accounts = [{"customer_id": r.split("/")[-1]} for r in resp.resource_names]
        return json.dumps(accounts, indent=2)
    except Exception as e:
        msg = str(e)[:200] if str(e) else "Unknown error"
        return json.dumps({"error": msg})


# ── Resource Templates ─────────────────────────────────────────────────────────


@mcp.resource("burnr8://accounts/{customer_id}/performance")
def account_performance(customer_id: str) -> str:
    """Campaign performance summary for the last 30 days — loaded as context automatically."""
    import json

    from burnr8.client import get_client
    from burnr8.helpers import micros_to_dollars, run_gaql

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
            cost = micros_to_dollars(int(m.get("cost_micros", 0)))
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
                "avg_cpa": round(total_spend / total_conversions, 2) if total_conversions > 0 else None,
                "campaigns": campaigns,
            },
            indent=2,
        )
    except Exception as e:
        msg = str(e)[:200] if str(e) else "Unknown error"
        return json.dumps({"error": msg})


@mcp.resource("burnr8://accounts/{customer_id}/keywords")
def account_keywords(customer_id: str) -> str:
    """Keyword health summary — quality scores, top performers, underperformers."""
    import json

    from burnr8.client import get_client
    from burnr8.helpers import micros_to_dollars, run_gaql

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
                    "spend": round(micros_to_dollars(int(m.get("cost_micros", 0))), 2),
                    "clicks": int(m.get("clicks", 0)),
                    "conversions": float(m.get("conversions", 0)),
                }
            )
        avg_qs = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None
        low_qs = [k for k in keywords if k["quality_score"] is not None and int(k["quality_score"]) < 5]
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
        msg = str(e)[:200] if str(e) else "Unknown error"
        return json.dumps({"error": msg})


@mcp.resource("burnr8://accounts/{customer_id}/structure")
def account_structure(customer_id: str) -> str:
    """Account structure — campaigns, ad groups, keyword counts, budget info."""
    import json

    from burnr8.client import get_client
    from burnr8.helpers import micros_to_dollars, run_gaql

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
        ag_counts = Counter(ag.get("campaign", {}).get("id") for ag in ad_groups)
        structure = []
        for row in campaigns:
            c = row.get("campaign", {})
            b = row.get("campaign_budget", {})
            cid = c.get("id")
            ag_count = ag_counts.get(cid, 0)
            structure.append(
                {
                    "campaign_id": cid,
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "channel_type": c.get("advertising_channel_type"),
                    "bidding_strategy": c.get("bidding_strategy_type"),
                    "daily_budget": round(micros_to_dollars(int(b.get("amount_micros", 0))), 2),
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
        msg = str(e)[:200] if str(e) else "Unknown error"
        return json.dumps({"error": msg})


# ── Prompts ────────────────────────────────────────────────────────────────────


@mcp.prompt
def audit(customer_id: str = "", target_cpa: str = "", monthly_budget: str = "") -> str:
    """Run a complete Google Ads account audit with the 74-check framework."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"
    if target_cpa:
        context += f", Target CPA: ${target_cpa}"
    if monthly_budget:
        context += f", Monthly budget: ${monthly_budget}"

    return f"""Run a full Google Ads audit. {context}

## Step 1: Pull all data
Call quick_audit first — it fetches campaigns, keywords, ads, negatives, conversions, and budgets in one call.

## Step 2: Score across 6 categories

### Conversion Tracking (25% weight)
- Is there exactly ONE primary conversion action? (multiple primaries confuse Smart Bidding)
- Is attribution model data-driven? (last-click is outdated)
- Are counting types consistent? (ONE_PER_CLICK for leads, MANY_PER_CLICK for purchases)
- Call list_conversion_goals to check what Smart Bidding is optimizing toward

### Wasted Spend (20% weight)
- What % of spend goes to keywords with 0 conversions?
- Are "free" intent queries blocked? (add "free" as Phrase Match negative)
- Call get_search_terms_report to find irrelevant queries
- Calculate monthly wasted spend in dollars

### Account Structure (15% weight)
- Are ad groups tightly themed? (15-20 keywords max)
- Do naming conventions exist?
- Any orphan budgets? (call remove_orphan_budgets with confirm=false to check)

### Keywords (15% weight)
- Average Quality Score: ≥7 = PASS, 5-6 = WARNING, <5 = FAIL
- Are top converters on Exact Match? (protect your winners)
- Any QS 1-2 keywords still enabled? (pause immediately)

### Ads (15% weight)
- Ad Strength: Good or Excellent = PASS, Average = WARNING, Poor = FAIL
- Are there 3+ RSAs per ad group?
- Call list_extensions — need ≥4 sitelinks, ≥4 callouts, structured snippets

### Settings (10% weight)
- Call get_geo_target_type_setting — should be PRESENCE not PRESENCE_OR_INTEREST
- Call list_device_bid_adjustments — are mobile/tablet adjusted?
- Is the budget being fully spent? (underspend = missed opportunity)

## Step 3: Present findings
Format as a health score report with:
- Overall score /100 with letter grade
- Per-category scores
- Quick wins sorted by estimated dollar impact
- Action items with specific tool calls to execute each fix"""


@mcp.prompt
def optimize(customer_id: str = "") -> str:
    """Find and fix wasted ad spend with specific negative keyword recommendations."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"

    return f"""Optimize Google Ads for wasted spend. {context}

## Step 1: Find wasted spend
Call cleanup_wasted_spend — returns keywords with spend but 0 conversions.

## Step 2: Analyze search terms
Call get_search_terms_report — look for:
- Free-intent queries ("free", "gratis", "no cost")
- Informational queries ("how to", "what is", "tutorial")
- Job-seeker queries ("jobs", "careers", "salary")
- Competitor queries (decide if intentional)
- Irrelevant industry queries

## Step 3: Recommend negative keywords
CRITICAL RULES:
- NEVER suggest Broad Match negatives — they block too broadly
- Default to Exact Match [keyword] for specific irrelevant queries
- Use Phrase Match "keyword" for irrelevant intent patterns
- Source from actual Search Terms Report, NOT guesses
- Group into themed lists: informational, job-seeker, competitor, free-intent

## Step 4: Recommend keyword pauses
Pause keywords that meet ALL of:
- Spend > $20 in the period
- 0 conversions
- Quality Score < 5 (or no QS data)

## Step 5: Present savings
- Total monthly wasted spend estimate
- Per-keyword breakdown (spend, clicks, 0 conversions)
- Specific negative keywords to add with match types
- Ask for confirmation before executing any changes"""


@mcp.prompt
def new_campaign(customer_id: str = "", product: str = "", url: str = "", daily_budget: str = "") -> str:
    """Plan and launch a new search campaign with best practices."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"

    return f"""Create a new Google Ads search campaign. {context}
Product/service: {product}
Landing page: {url}
Daily budget: {daily_budget if daily_budget else "Ask the user"}

## Step 1: Keyword Research
Call research_keywords with seed keywords from the product description.
Evaluate results by:
- Monthly search volume (ignore <100/mo)
- Competition level (prefer LOW/MEDIUM for new campaigns)
- Top-of-page bid (sets CPC expectations)

## Step 2: Campaign Structure
Recommend themed ad groups. Each ad group should:
- Have 5-15 tightly related keywords
- Share a common intent (e.g., "buy X" vs "X reviews")
- Start with Broad Match + Maximize Conversions (Smart Bidding needs data)

## Step 3: Write Ad Copy
Write 15 headlines (max 30 chars each) and 4 descriptions (max 90 chars each):
- Headlines: include keyword, CTA, price/offer, differentiator, social proof
- Descriptions: expand on value prop, include CTA, address objections
- Do NOT pin headlines unless strategically necessary (reduces RSA flexibility)

## Step 4: Launch
Call launch_campaign with all components. It creates:
- Budget (daily, non-shared)
- Campaign (PAUSED, Search, with correct network settings)
- Ad group with keywords (Broad match)
- Responsive Search Ad

## Step 5: Post-Launch Checklist
- Confirm campaign is PAUSED
- Verify geo targeting: call get_geo_target_type_setting → should be PRESENCE
- Recommend: add sitelinks (4+), callouts (4+), structured snippets
- Remind: enable campaign only when ready (set_campaign_status requires confirm=true)
- Set expectations: wait 2 weeks for learning phase before optimizing"""


@mcp.prompt
def budget_reallocation(customer_id: str = "") -> str:
    """Analyze budget allocation and recommend where to move spend."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"
    return f"""Analyze budget allocation. {context}

## Step 1: Pull performance data
Call get_campaign_performance with LAST_30_DAYS for all campaigns.
Call list_budgets to see daily budget amounts.

## Step 2: Identify budget-constrained campaigns
Look for campaigns where:
- Spend is consistently near the daily budget (>90% utilization)
- CPA is below target (good performance, just needs more budget)
- Impression share loss due to budget is high (use run_gaql_query with metrics.search_budget_lost_impression_share)

## Step 3: Identify underspending campaigns
Look for campaigns where:
- Spend is well below daily budget (<50% utilization)
- CPA is above target or conversions are low

## Step 4: Recommend reallocations
Present as a table:
| Campaign | Current Budget | Spend | CPA | Recommendation | New Budget |
Show total budget stays the same — just redistributed.

## Step 5: Estimate impact
Calculate: if we move $X from low-ROI to high-ROI, estimated additional conversions at the high-ROI campaign's CPA.
Ask for confirmation before making any changes."""


@mcp.prompt
def ad_copy(customer_id: str = "", campaign_id: str = "") -> str:
    """Generate new RSA ad variations based on current performance."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"
    campaign_context = f", Campaign: {campaign_id}" if campaign_id else ""
    return f"""Generate new ad copy variations. {context}{campaign_context}

## Step 1: Analyze current ads
Call list_ads to get existing RSA headlines and descriptions.
Call get_campaign_performance to identify the best-performing campaign/ad group.

## Step 2: Identify what's working
Look at the top-performing ad's headlines and descriptions. Categorize each by angle:
- CTA ("Start Free", "Try Now")
- Price/Offer ("$9.99/mo", "7-Day Free Trial")
- Social Proof ("Join 5,000+ Users", "Rated #1")
- Feature ("AI-Powered", "1200+ Questions")
- Pain Point ("Stop Wasting Time", "Struggling With...")
- Differentiator ("Unlike UWorld", "No Credit Card")

## Step 3: Generate new variations
Write 15 headlines (max 30 chars each) and 4 descriptions (max 90 chars each) using these frameworks:
- Problem-Agitate-Solve: state the problem, make it urgent, offer the solution
- Before-After-Bridge: current state → desired state → your product as the bridge
- Social Proof Lead: impressive stat → what you do → CTA
- Question Hook: ask a question the user is thinking → answer with your product

Ensure variety across angles — don't write 15 CTA headlines.

## Step 4: Recommend placement
Suggest which ad group to add the new RSA to.
Offer to create via create_responsive_search_ad.

## Rules
- Every headline must be ≤30 characters
- Every description must be ≤90 characters
- Do NOT pin headlines unless strategically necessary
- Include at least 2 headlines with the primary keyword"""


@mcp.prompt
def trends(customer_id: str = "") -> str:
    """Detect week-over-week performance changes and anomalies."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"
    return f"""Detect performance trends and anomalies. {context}

## Step 1: Compare this week vs last week
Call get_campaign_performance with LAST_7_DAYS.
Call get_campaign_performance with LAST_14_DAYS and subtract this week's data to get last week's numbers. Note: this gives approximate results. For exact 7-day comparison, use run_gaql_query with explicit date ranges (e.g. segments.date BETWEEN '2026-03-28' AND '2026-04-03').

## Step 2: Calculate week-over-week changes
For each campaign, calculate % change in:
- Spend
- CPA (cost per conversion)
- CTR
- Conversions
- Impressions

## Step 3: Flag anomalies
Flag anything with >20% week-over-week change:
- 🔴 CPA increased >20% — investigate immediately
- 🟢 CPA decreased >20% — understand why (replicate if intentional)
- 🔴 CTR dropped >20% — ad fatigue? audience shift?
- 🟡 Spend increased >20% without conversion increase — waste risk

## Step 4: Check for new patterns
Call get_search_terms_report LAST_7_DAYS — any new high-spend search terms that weren't there before?
Call get_keyword_performance — any Quality Score drops?

## Step 5: Present findings
Table format:
| Campaign | Metric | Last Week | This Week | Change | Flag |
Sort by severity (biggest negative changes first).
End with recommended actions for each flagged item."""


@mcp.prompt
def competitors(customer_id: str = "", campaign_id: str = "") -> str:
    """Analyze competitive positioning — impression share, lost opportunities, and competitor domains."""
    context = f"Account: {customer_id}" if customer_id else "Use the active account"
    campaign_filter = f", Campaign: {campaign_id}" if campaign_id else ""

    return f"""Analyze competitive positioning in Google Ads. {context}{campaign_filter}

## Step 1: Pull impression share data
Call get_competitive_metrics — this works for ALL accounts and shows:
- Search impression share (% of eligible impressions you received)
- Top/absolute top impression share (ad position quality)
- Budget-lost impression share (impressions lost because budget ran out)
- Rank-lost impression share (impressions lost due to low Quality Score or bids)

## Step 2: Try auction insights (if available)
Call get_auction_insights for the top-spending campaign — this shows specific competitor domains.
If it returns an allowlisting error, skip this step and note it's unavailable.

## Step 3: Analyze competitive gaps
For each campaign, identify:
- **Budget-limited campaigns**: budget_lost_impression_share > 10% = you're leaving impressions on the table
- **Rank-limited campaigns**: rank_lost_impression_share > 20% = competitors outbid or outrank you
- **Low absolute top share**: abs_top_impression_share < 30% = you rarely appear as the first ad
- **Exact match weakness**: exact_match_impression_share much lower than broad = your exact keywords aren't competitive

## Step 4: Cross-reference with performance
Call get_campaign_performance for the same date range. Compare:
- Are high-impression-share campaigns also high-converting?
- Are budget-limited campaigns the ones with best CPA? (If yes, increase budget immediately)
- Are rank-limited campaigns worth fighting for? (Check CPA — if profitable, improve QS or raise bids)

## Step 5: Present competitive intelligence report
Format as:

### Competitive Position Summary
| Campaign | IS% | Top IS% | Budget Lost | Rank Lost | Action |
|----------|-----|---------|-------------|-----------|--------|

### Opportunities (sorted by estimated impact)
1. [Campaign X] — Losing Y% of impressions to budget. Estimated Z additional clicks/month at current CTR.
2. [Campaign Y] — Rank-limited. QS improvement from 5→7 would recover ~N% impression share.

### Competitor Landscape (if auction insights available)
| Competitor | Their IS% | Overlap | They Outrank You | You Outrank Them |
|------------|-----------|---------|------------------|------------------|

### Recommended Actions
- Budget changes (with specific dollar amounts)
- QS improvement targets (which keywords to focus on)
- Bid strategy adjustments
- Ask for confirmation before executing any changes"""


if __name__ == "__main__":
    mcp.run()
