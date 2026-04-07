---
name: google-ads-optimize
description: Google Ads wasted spend optimization using burnr8 MCP tools. Negative keyword strategy, keyword pausing criteria, and budget reallocation.
license: MIT
metadata:
  version: 0.6.1
  author: Harrison Hesslink
  category: advertising
  updated: 2026-04-05
---

# Google Ads Optimization

Use this skill with the burnr8 MCP tools to find and fix wasted ad spend.

## Workflow

1. Call `cleanup_wasted_spend` to identify non-converting keywords
2. Call `get_search_terms_report` to find irrelevant queries
3. Apply the rules below to build negative keyword and pause recommendations
4. Present savings estimate before executing changes

## Negative Keyword Rules

CRITICAL — bad negatives kill campaigns:

- **NEVER suggest Broad Match negatives** — they block too broadly
- Default to **Exact Match** `[keyword]` for specific irrelevant queries
- Use **Phrase Match** `"keyword"` for irrelevant intent patterns
- Source negatives from the actual Search Terms Report, NOT guesses
- Group into themed lists:
  - Informational: "how to", "what is", "tutorial", "DIY"
  - Job-seeker: "jobs", "careers", "salary", "hiring"
  - Free-intent: "free", "crack", "torrent", "no cost"
  - Competitor: only if intentionally excluded
- Review existing negatives for over-blocking before adding more

## Keyword Pause Criteria

Pause a keyword when ALL of these are true:
- Spend > $20 in the period
- 0 conversions
- Quality Score < 5 (or no QS data)

Do NOT pause keywords that:
- Have conversions (even 1)
- Have QS >= 7 (they may just need better ads)
- Are brand terms (protect regardless of metrics)

## Budget Reallocation

After identifying waste:
1. Calculate monthly wasted spend in dollars
2. Identify budget-constrained campaigns (use `get_competitive_metrics` — look for `budget_lost_impression_share > 10%`)
3. Recommend moving budget from wasted areas to constrained winners
4. Show total budget stays the same — just redistributed

## Presenting Recommendations

Always present as:

| Keyword | Spend | Clicks | Conversions | QS | Action |
|---------|-------|--------|-------------|----|---------| 

Sort by spend descending. Show estimated monthly savings.
Ask for confirmation before executing any changes.
