# PropScout — Design

> A self-hostable tool that takes a search ("3bd cabin near Asheville under $500k, good for Airbnb"),
> fans out scrapers + cheap LLM research agents, and returns ranked purchase opportunities —
> homes and cabins first, then land, rentals, and small businesses. Alerts go to Telegram.

Status: **V0** (CLI → CSV) implemented. Everything below "V1" is design only.

---

## 1. Goals

| Goal | Notes |
|---|---|
| Structured + natural-language search | location, price, beds/baths, sqft, lot, year, property type, free-text "notes" for the agent |
| Multi-strategy scoring | short-term rental (STR), long-term rental (LTR), personal use + appreciation, land/development |
| $0 data budget for V0 | Open-source scrapers + free public data. Paid APIs are optional, pluggable fallbacks |
| Cheap LLMs | OpenRouter, DeepSeek / Qwen / Gemini Flash-Lite tier. Target < $0.01 per search |
| Easy self-hosting | Single Docker image; Railway (worker + Postgres + cron) for always-on mode |
| Alerts | Telegram bot (free, two-way). iMessage/SMS can be added as another `Notifier` |

Non-goals (for now): multi-user SaaS, auth, MLS/IDX licensing, automated offers.

---

## 2. Data source research (Nov 2026)

### Listings (for sale)

| Source | Cost | How | Verdict |
|---|---|---|---|
| **[HomeHarvest](https://github.com/Bunsly/HomeHarvest)** (Realtor.com) | Free, OSS (MIT) | `pip install homeharvest`; server-side filters for price, beds, baths, sqft, lot, year, property type (incl. `land`, `farm`); returns ~70 cols incl. `estimated_value`, `tax`, `hoa_fee`, lat/lng, listing description, photos | **V0 primary.** Verified working (v0.8.18). Can 403 under heavy use → throttle / optional proxy |
| Zillow official API | — | Public ZWSID API retired 2021; Bridge Interactive API requires approval | Not viable |
| Zillow via Apify actors | ~$5 free credit/mo, then pay-per-result | REST | Paid fallback adapter |
| Zillapi / HasData Zillow API (+ [HasData zillow-mcp](https://github.com/HasData/zillow-mcp)) | Small free tier, then paid | REST / MCP | Paid fallback adapter |
| Redfin (unofficial "stingray" endpoints) | Free | Scrape | Possible second free source; brittle |
| LandWatch / Land.com | Free | Scrape (Playwright) | V3 for land |
| BizBuySell | Free | Scrape (Playwright) | V3 for businesses |

### Comps, rents, valuation

| Need | Free source | Paid upgrade |
|---|---|---|
| Rent comps (LTR) | HomeHarvest `listing_type="for_rent"` (mostly price *ranges*; beds often missing) | RentCast (free dev tier ~50 calls/mo, then paid) |
| Rent floor | HUD Fair Market Rents API (free token) by county + bedroom count | — |
| Sale comps / $ per sqft | HomeHarvest `listing_type="sold", past_days=180` | ATTOM, HouseCanary |
| Valuation | Realtor.com `estimated_value` (in HomeHarvest output) | RentCast AVM |
| STR revenue (Airbnb) | `pyairbnb` (unofficial, free) → nearby listings, nightly price, calendar availability → occupancy proxy | Apify Airbnb occupancy actors (~$0.50–5 / 1k results), AirDNA |

### Market + risk context (all free)

| Data | Source |
|---|---|
| Mortgage rates | FRED `MORTGAGE30US` (free key) |
| Demographics, income, population growth, vacancy | Census ACS API (free key) |
| Jobs / unemployment | BLS API, FRED county series |
| Flood zone | FEMA National Flood Hazard Layer (ArcGIS REST, point query by lat/lng) |
| Parcels / zoning | County GIS portals (free, inconsistent); Regrid (paid) for nationwide parcels |
| General web research | Search API with free tier (Tavily / Brave / Exa — verify current limits) + Jina Reader for page → markdown |

### Existing MCP servers worth reusing later
- Zillow MCPs: HasData/zillow-mcp, sap156/zillow-mcp-server (various maturity; most wrap paid APIs).
- Apify's Real Estate MCP (Redfin-based, pay-per-use).

Decision: **don't depend on MCP servers at runtime** for V0–V1 (extra moving parts, mostly paid). Instead expose *our own* sources as agent tools, and later publish PropScout itself as an MCP server (V3).

### LLMs via OpenRouter (prices per 1M tokens, checked against the OpenRouter models API)

| Model | In / Out | Use |
|---|---|---|
| `deepseek/deepseek-v4.1-flash` | ~$0.05 / $0.57 | **Default** analyst + query parser; tool calling + JSON |
| `qwen/qwen3.8-flash` | ~$0.15 / $0.47 | Fallback #1 |
| `google/gemini-2.5-flash-lite` | ~$0.10 / $0.40 | Fallback #2 |
| `z-ai/glm-5.3-flash`, `qwen/qwen3.7-flash` | ~$0.03 / $0.10 | Ultra-cheap bulk triage (V2) |

OpenRouter's `models` array gives automatic fallback when a provider errors. Analysing ~20 listings at ~2k tokens each costs well under $0.01.

---

## 3. Architecture

```
                ┌──────────────────────────── V0 (today) ──────────────────────────────┐
 CLI / prompt ─▶│ QueryParser(LLM) ─▶ SearchQuery                                       │
                │        │                                                             │
                │        ▼                                                             │
                │  Sources ── RealtorSource (HomeHarvest)  [Zillow/Apify adapters V1+] │
                │        │                                                             │
                │        ▼                                                             │
                │  Enrichment ── rent comps (for_rent) · sale comps (sold 180d)        │
                │        │                                                             │
                │        ▼                                                             │
                │  Finance (deterministic): mortgage, NOI, cap rate, CoC, $/sqft gap   │
                │        │                                                             │
                │        ▼                                                             │
                │  Prescore (0–100, strategy-weighted)  → top N                        │
                │        │                                                             │
                │        ▼                                                             │
                │  AnalystAgent (LLM, parallel) → score, best strategy, thesis, risks  │
                │        │                                                             │
                │        ▼                                                             │
                │  Exporters: CSV + Markdown report      Notifier: Telegram (optional) │
                └──────────────────────────────────────────────────────────────────────┘
```

Key principle: **numbers are computed deterministically in Python; the LLM only interprets.**
LLMs are cheap but bad at arithmetic, and deterministic prescoring means we only pay to analyse the top N.

### Module layout

```
src/propscout/
  models.py        SearchQuery, Strategy, Analysis (pydantic)
  config.py        env-driven settings (OPENROUTER_API_KEY, TELEGRAM_*, finance assumptions)
  sources/         Source protocol + RealtorSource (HomeHarvest)
  analysis/
    comps.py       rent + $/sqft comps with fallback chain
    finance.py     mortgage / NOI / cap rate / cash-on-cash
    scoring.py     strategy-weighted prescore
  agents/
    llm.py         OpenRouter client (OpenAI SDK), JSON mode, model fallback
    parser.py      natural language → SearchQuery
    analyst.py     per-listing investment memo
  notify/telegram.py
  pipeline.py      orchestration
  export.py        CSV + Markdown
  cli.py           `propscout search ...`
```

### Rent estimate fallback chain
1. Rent comps in same ZIP with same bed count (≥ 3 samples) → median
2. Rent comps in search area with same bed count (≥ 3) → median
3. Rent comps in same ZIP, single-family/townhome only → median
4. *(V1)* HUD Fair Market Rent for county + beds
5. Otherwise blank (no fabricated numbers)

Rent listings frequently publish a range; we use the midpoint.

### Prescore (0–100)
Weighted sum of normalised signals; weights depend on the requested strategies:

| Signal | LTR | STR* | Appreciation | Land |
|---|---|---|---|---|
| Cap rate / cash-on-cash | high | med | low | — |
| Discount vs `estimated_value` | med | med | high | med |
| $/sqft vs ZIP sold median | med | med | high | — |
| Days on market (negotiability) | low | low | med | med |
| Lot size per $ | — | low | low | high |

\*STR uses LTR economics as a proxy until STR comps land in V2.

---

## 4. Roadmap

### V0 — CLI → CSV ✅
- `propscout search --location ... --price-max ... --beds-min ...` or `propscout search --prompt "..."`
- HomeHarvest listings + rent/sold comps, deterministic finance + prescore, LLM memo on top N
- `results/<timestamp>_<slug>.csv` + `.md` report; optional Telegram summary

### V1 — Always-on watches (Railway)
- **Postgres** tables: `watches` (saved SearchQuery + cron), `listings` (property_id PK, latest snapshot), `listing_events` (new, price_drop, back_on_market), `analyses`
- **Scheduler**: Railway cron service runs `propscout run-watches` every N hours → diff vs last snapshot → analyse only new/changed → alert
- **Telegram bot** (long polling or webhook on FastAPI): `/watch <prompt>`, `/watches`, `/pause <id>`, `/top <id>`, reply-to-alert "tell me more" → deeper research
- **FastAPI**: CRUD for watches, `/runs/{id}` results, health check
- Dedup, retries with backoff, polite rate limiting, optional proxy
- HUD FMR + FRED rate + FEMA flood zone enrichment

### V2 — Research agents
- Tool-calling **ResearchAgent** (OpenRouter function calling) with tools: `web_search`, `fetch_page`, `flood_zone`, `census_profile`, `str_comps` (pyairbnb), `sale_comps`, `county_zoning_lookup`
- Strategy-specific memo templates (STR regs, permitting, HOA rental bans, road access for cabins)
- Two-tier model routing: ultra-cheap model triages, DeepSeek/Qwen does deep dives, budget cap per run
- Optional Next.js dashboard on Vercel (reads from the FastAPI) — map view, compare, notes

### V3 — More asset classes + ecosystem
- Land (LandWatch/Land.com + parcel data), small businesses (BizBuySell), multifamily
- Export PropScout as an **MCP server** so Claude/other agents can query it
- Additional notifiers: iMessage (Mac relay via BlueBubbles/AppleScript), SMS (Twilio), email

---

## 5. Deployment

| Option | Fit |
|---|---|
| **Railway** (recommended) | Docker image; services: `api` (FastAPI + Telegram webhook), `cron` (`propscout run-watches`), Postgres plugin. ~$5/mo Hobby. No function timeouts — scraping runs can take minutes |
| Vercel | Only for the optional dashboard. Serverless timeouts make it a poor fit for scraping/agent runs |
| Local / home server | `docker compose up` with SQLite or Postgres; cron via the container |

Config is entirely environment variables (`.env.example`), so the same image runs locally and on Railway.

---

## 6. Risks & guardrails
- **Scraper breakage / blocking**: sources behind a `Source` interface; multiple adapters; throttle; cache responses; proxy support.
- **Terms of service**: personal, low-volume use; don't redistribute scraped data; respect rate limits. Users are responsible for compliance in their jurisdiction.
- **LLM hallucination**: memos get structured facts only; numeric fields come from code; JSON schema validation; "insufficient data" is an allowed answer.
- **Cost runaway**: per-run token budget, prescore gate (`--analyze-top`), cheap default models.
