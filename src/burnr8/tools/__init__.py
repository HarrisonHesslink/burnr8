from burnr8.tools.accounts import register as register_accounts
from burnr8.tools.ad_groups import register as register_ad_groups
from burnr8.tools.adjustments import register as register_adjustments
from burnr8.tools.ads import register as register_ads
from burnr8.tools.budgets import register as register_budgets
from burnr8.tools.campaigns import register as register_campaigns
from burnr8.tools.competitive import register as register_competitive
from burnr8.tools.compound import register as register_compound
from burnr8.tools.conversions import register as register_conversions
from burnr8.tools.extensions import register as register_extensions
from burnr8.tools.goals import register as register_goals
from burnr8.tools.keywords import register as register_keywords
from burnr8.tools.negative_keywords import register as register_negative_keywords
from burnr8.tools.reporting import register as register_reporting


def register_all_tools(mcp):
    register_accounts(mcp)
    register_campaigns(mcp)
    register_ad_groups(mcp)
    register_ads(mcp)
    register_keywords(mcp)
    register_negative_keywords(mcp)
    register_budgets(mcp)
    register_reporting(mcp)
    register_extensions(mcp)
    register_conversions(mcp)
    register_compound(mcp)
    register_adjustments(mcp)
    register_goals(mcp)
    register_competitive(mcp)
