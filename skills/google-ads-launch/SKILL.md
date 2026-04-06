---
name: google-ads-launch
description: Google Ads campaign launch best practices using burnr8 MCP tools. Keyword research, ad group structure, RSA copy, and post-launch checklist.
license: MIT
metadata:
  version: 0.6.1
  author: Harrison Hesslink
  category: advertising
  updated: 2026-04-05
---

# Campaign Launch Guide

Use this skill with the burnr8 MCP tools to plan and launch a new search campaign.

## Pre-Launch Checklist

Before launching, confirm with the user:
- What product/service is being promoted?
- What is the landing page URL?
- What is the daily budget?
- What is the target CPA or ROAS?
- Who is the ideal customer?

## Step 1: Keyword Research

Call `research_keywords` with seed keywords from the product description.

Evaluate results by:
- Monthly search volume: ignore < 100/mo
- Competition level: prefer LOW/MEDIUM for new campaigns
- Top-of-page bid: sets CPC expectations

NOTE: `research_keywords` requires an account with active campaigns and billing enabled. If it returns empty results, ask the user for keywords manually.

## Step 2: Campaign Structure

Recommend themed ad groups. Each ad group should:
- Have 5-15 tightly related keywords
- Share a common intent (e.g., "buy X" vs "X reviews")
- Start with **Broad Match + Maximize Conversions** (Smart Bidding needs data)

Do NOT create SKAGs (single keyword ad groups) — they fragment data and hurt Smart Bidding.

## Step 3: Write Ad Copy

Write 15 headlines (max 30 chars each) and 4 descriptions (max 90 chars each).

Headline angles — use variety across all of these:
- **Keyword**: include the primary keyword verbatim
- **CTA**: "Start Free", "Try Now", "Get Started"
- **Price/Offer**: "$9.99/mo", "7-Day Free Trial"
- **Social Proof**: "Join 5,000+ Users", "Rated #1"
- **Feature**: "AI-Powered", "1200+ Questions"
- **Pain Point**: "Stop Wasting Time", "Struggling With..."
- **Differentiator**: "Unlike Competitor", "No Credit Card"

Do NOT pin headlines unless strategically necessary — it reduces RSA flexibility.

## Step 4: Launch

Call `launch_campaign` with all components. It creates:
- Budget (daily, non-shared, explicitly_shared=false)
- Campaign (PAUSED, Search, correct network settings)
- Ad group with keywords (Broad match)
- Responsive Search Ad

## Step 5: Post-Launch Checklist

After launch_campaign succeeds:
1. Confirm campaign is PAUSED (it always starts paused)
2. Verify geo targeting: call `get_geo_target_type_setting` — should be PRESENCE not PRESENCE_OR_INTEREST
3. Recommend adding extensions:
   - 4+ sitelinks (call `create_sitelink`)
   - 4+ callouts (call `create_callout`)
   - Structured snippets (call `create_structured_snippet`)
4. Remind user: enable campaign only when ready (`set_campaign_status` requires confirm=true)
5. Set expectations: wait 2 weeks for learning phase before optimizing
