# Project Guide

## Overview

This project monitors X with recent search, detects timing-related boxing or MMA tweets, and sends them to Slack.

Main functions:

- X API v2 recent search
- configurable matching rules
- Slack alerts with `Open X`, `Reply A`, `Reply B`, `Ignore`
- SQLite dedupe
- estimated daily API budget cap
- slash commands for `health`, `usage`, and `poll`

## Main Files

- `main.py` - entry point
- `config.json` - matching rules, templates, limits
- `.env.example` - environment variable template
- `requirements.txt` - Python dependencies
- `data/` - runtime database is created here automatically
- `DOCS/CLIENT_SETUP.md` - full setup guide for Slack, X, and hosting

## Commands

```bash
python main.py preview
python main.py poll-once
python main.py serve
python main.py usage
python main.py tweets
python main.py x-auth-url
python main.py x-auth-status
python -m pytest
```

## Slack Commands

Use the slash command configured in Slack:

```text
/fightbot help
/fightbot health
/fightbot usage
/fightbot poll
```

## Config You Should Review

- `matcher.fighter_names`
- `matcher.timing_phrases`
- `matcher.target_terms`
- `reply_templates.a`
- `reply_templates.b`
- `limits.search_request_cost_usd`
- `limits.reply_request_cost_usd`
- `limits.daily_cost_cap_usd`

## Reply Behavior

- `Reply A` posts the exact text from `config.json -> reply_templates.a`
- `Reply B` posts the exact text from `config.json -> reply_templates.b`
- `Open X` opens the matched post directly in X
- `Ignore` marks the tweet as ignored
- processed tweet IDs are stored in SQLite to prevent duplicate replies

## X Limitation

As of February 23, 2026, X restricted many programmatic replies on self-serve API tiers.

Practical result for this project:

- detection flow works
- Slack alerts work
- `Open X` works
- some API replies to arbitrary public search matches may still be rejected by X

Official references:

- X Developers announcement: https://x.com/XDevelopers/status/2026084506822730185
- X automation rules: https://help.x.com/en/rules-and-policies/x-automation
- X Create Post docs: https://docs.x.com/x-api/posts/create-post

## Hosting

Recommended option: Render Web Service.

Why:

- always-on process
- public HTTPS URL
- simple environment variable management

References:

- Render pricing: https://render.com/pricing
- Render web services: https://render.com/docs/web-services

## Quick Start

1. Copy `.env.example` to `.env`
2. Review `config.json`
3. Follow `DOCS/CLIENT_SETUP.md`
4. Start:

```bash
python main.py serve
```
