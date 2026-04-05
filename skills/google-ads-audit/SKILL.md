---
name: google-ads-audit
description: Google Ads account audit using burnr8 MCP tools. 74-check framework across conversion tracking, wasted spend, account structure, keywords, ads, and settings.
license: MIT
metadata:
  version: 0.5.0
  author: Harrison Hesslink
  category: advertising
  updated: 2026-04-04
---

# Google Ads Audit

Use this skill with the burnr8 MCP tools to perform a comprehensive Google Ads account audit.

## Quick Start

1. Call `quick_audit` with the customer_id for a full account snapshot
2. Review the health score and findings below
3. Execute fixes using burnr8 tools

## Audit Framework (74 checks, 6 categories)

### 1. Conversion Tracking (25% weight)
- Conversion actions mapped correctly (primary vs secondary)
- Attribution model: data-driven preferred
- Counting type consistency (ONE_PER_CLICK vs MANY_PER_CLICK)
- Value settings configured
- **Tools:** `list_conversion_actions`, `get_conversion_action`, `list_conversion_goals`

### 2. Wasted Spend (20% weight)
- Search terms with spend but 0 conversions
- Missing negative keywords for irrelevant queries
- "Free" intent traffic not blocked
- Broad match only with Smart Bidding
- **Tools:** `get_search_terms_report`, `cleanup_wasted_spend`, `list_negative_keywords`, `add_negative_keywords`

### 3. Account Structure (15% weight)
- Campaign naming conventions
- Ad group theming (15-20 keywords max)
- RSA count per ad group (3+ recommended)
- Orphan budgets
- **Tools:** `list_campaigns`, `list_ad_groups`, `list_budgets`, `remove_orphan_budgets`

### 4. Keywords (15% weight)
- Quality Score distribution (target avg 7+)
- Match type strategy (Exact for winners, Broad for discovery)
- Keyword cannibalization
- Low QS keywords (< 5 = FAIL)
- **Tools:** `list_keywords`, `get_keyword_performance`, `research_keywords`, `pause_keyword`

### 5. Ads (15% weight)
- RSA ad strength: Good or Excellent
- 3-15 headlines, 2-4 descriptions per RSA
- Extensions: sitelinks (4+), callouts (4+), structured snippets
- **Tools:** `list_ads`, `list_extensions`, `create_sitelink`, `create_callout`

### 6. Settings (10% weight)
- Bid strategy appropriate for campaign maturity
- Budget pacing (not limited by budget unless intentional)
- Location targeting: PRESENCE not PRESENCE_OR_INTEREST
- Search partners / Display network reviewed
- Device bid adjustments set
- **Tools:** `get_campaign`, `update_campaign`, `list_device_bid_adjustments`, `get_geo_target_type_setting`, `list_ad_schedules`

## Key Thresholds

| Metric | Pass | Warning | Fail |
|--------|------|---------|------|
| Quality Score (avg) | >=7 | 5-6 | <5 |
| CTR (Search) | >=5% | 3-5% | <3% |
| Wasted Spend | <10% | 10-20% | >20% |
| Ad Strength | Good+ | Average | Poor |

## Scoring

```
Health Score: XX/100 (Grade: X)

Conversion Tracking: XX/100  (25%)
Wasted Spend:        XX/100  (20%)
Account Structure:   XX/100  (15%)
Keywords:            XX/100  (15%)
Ads:                 XX/100  (15%)
Settings:            XX/100  (10%)
```

## Negative Keyword Best Practices

- Default to Exact Match `[keyword]` for specific irrelevant queries
- Use Phrase Match `"keyword"` for irrelevant intent patterns
- Source from actual Search Terms Report, NOT guesses
- NEVER use Broad Match negatives unless explicitly justified
- Group into themed lists: informational, job-seeker, competitor, free-intent
