---
name: google-ads-competitors
description: Google Ads competitive analysis using burnr8 MCP tools. Impression share interpretation, competitive gaps, and positioning strategy.
license: MIT
metadata:
  version: 0.6.1
  author: Harrison Hesslink
  category: advertising
  updated: 2026-04-05
---

# Competitive Analysis

Use this skill with the burnr8 MCP tools to analyze competitive positioning.

## Key Metrics

Call `get_competitive_metrics` to pull impression share data. Here's what each metric means:

| Metric | What It Means | Good | Warning | Action |
|--------|---------------|------|---------|--------|
| `impression_share` | % of eligible impressions you received | > 70% | 40-70% | < 40% |
| `top_impression_share` | % shown above organic results | > 50% | 25-50% | < 25% |
| `abs_top_impression_share` | % shown as the very first ad | > 30% | 15-30% | < 15% |
| `budget_lost_impression_share` | % lost because budget ran out | < 5% | 5-15% | > 15% |
| `rank_lost_impression_share` | % lost due to low QS or bids | < 15% | 15-30% | > 30% |
| `exact_match_impression_share` | IS for exact match queries only | > 80% | 50-80% | < 50% |

## Interpreting Results

### Budget-Limited (budget_lost > 10%)
The campaign is profitable but underfunded. Every impression lost to budget is a missed conversion at your current CPA.

**Action**: Increase daily budget or reallocate from lower-performing campaigns. Use `list_budgets` and `update_budget` to adjust.

### Rank-Limited (rank_lost > 20%)
Competitors outbid or outrank you. This is either a bid problem or a Quality Score problem.

**Diagnose**: Call `get_keyword_performance` and check Quality Scores.
- QS < 5: Ad relevance or landing page issue — fix the ad copy and landing page before raising bids
- QS >= 7: Pure bid competition — consider raising bids or switching to a target impression share strategy

### Low Exact Match IS
If `exact_match_impression_share` is much lower than overall IS, your exact keywords aren't competitive. This often means competitors are bidding on your exact terms.

**Action**: Ensure top-converting keywords are on Exact Match with adequate bids.

## Auction Insights (If Available)

Call `get_auction_insights` for competitor domain-level data. This requires Google API allowlisting (most accounts don't have access). If it returns an error, use `get_competitive_metrics` instead.

When available, auction insights show:
- Which competitor domains appear alongside your ads
- Their impression share vs yours
- How often they outrank you
- How often you outrank them

## Presenting Results

Format as:

### Competitive Position Summary
| Campaign | IS% | Top IS% | Budget Lost | Rank Lost | Action |
|----------|-----|---------|-------------|-----------|--------|

### Opportunities (sorted by estimated impact)
Calculate: if budget_lost = 20% and current clicks = 100, recovering that share = ~25 additional clicks at current CTR.

Always ask for confirmation before executing budget or bid changes.
