# PropScout 🏡🔎

Self-hostable real estate opportunity finder. Give it a location + filters (or a plain-English
prompt), and it scrapes listings, pulls rent and sale comps, underwrites every property, ranks
them, and has a cheap LLM write an investment memo for the best ones. Output: CSV + Markdown
report, optionally pushed to Telegram.

- **$0 data**: listings and comps via the open-source [HomeHarvest](https://github.com/Bunsly/HomeHarvest) (Realtor.com) scraper — no API keys
- **Cheap agents**: OpenRouter with DeepSeek / Qwen / Gemini Flash-Lite (fractions of a cent per search)
- **Numbers in code, judgement in the LLM**: mortgage, NOI, cap rate, cash-on-cash and value gaps are computed deterministically; the model only interprets
- **Strategies**: short-term rental, long-term rental, appreciation/personal use, land

See [docs/DESIGN.md](docs/DESIGN.md) for the data-source research, architecture and roadmap
(always-on watches on Railway, Telegram bot commands, tool-using research agents, land &
businesses).

## Quick start

```bash
git clone https://github.com/ybshah02/propscout && cd propscout
uv venv && uv pip install -e .          # or: python -m venv .venv && pip install -e .
cp .env.example .env                    # add OPENROUTER_API_KEY for AI analysis (optional)
```

Structured search (works with no keys at all):

```bash
propscout search -l "Gatlinburg, TN" --price-max 600000 --beds-min 2 \
  --type single_family -s str,appreciation -n "mountain views, hot tub" -a 10
```

Natural-language search (needs `OPENROUTER_API_KEY`):

```bash
propscout search -p "3-4 bed cabin within Asheville NC under 550k, good Airbnb potential, near hiking"
```

Land:

```bash
propscout search -l "Madison County, NC" --type land,farm --lot-sqft-min 217800 --price-max 250000 -s land
```

Results land in `results/<timestamp>_<location>.csv` and `.md`.

### Options

| Flag | Meaning |
|---|---|
| `-p/--prompt` | Plain-English query, parsed by the LLM into filters |
| `-l/--location` | `"City, ST"`, ZIP, county, or address |
| `--price-min/max`, `--beds-min/max`, `--baths-min`, `--sqft-min/max`, `--lot-sqft-min`, `--year-built-min` | Filters (applied server-side) |
| `-t/--type` | `single_family,condos,townhomes,multi_family,duplex_triplex,land,farm,mobile` |
| `-s/--strategies` | `str,ltr,appreciation,land` — changes scoring weights and the memo |
| `-n/--notes` | Soft preferences for the analyst ("walkable", "creek frontage") |
| `-a/--analyze-top` | How many top-prescored listings the LLM analyses (default 10, 0 = off) |
| `--model` | Any OpenRouter model id |
| `--notify` | Send the top 5 to Telegram |
| `--all-columns` | Keep all ~70 scraped columns in the CSV |

Flags override anything parsed from `--prompt`.

### Telegram alerts

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`
2. Send your new bot any message, open `https://api.telegram.org/bot<TOKEN>/getUpdates`, copy `chat.id` into `TELEGRAM_CHAT_ID`
3. `propscout notify-test`, then add `--notify` to searches

## How ranking works

1. **Search**: Realtor.com for-sale listings matching your filters
2. **Comps**: for-rent listings (rent estimate: same ZIP + beds → area + beds → ZIP houses → none) and sold listings from the last 180 days ($/sqft by ZIP)
3. **Underwrite**: 20% down, 6.5% 30-yr, taxes (actual or 1.1%), insurance, HOA, vacancy, maintenance, capex, management (all configurable in `.env`)
4. **Prescore 0–100**: strategy-weighted mix of cap rate, cash-on-cash, discount to Realtor.com's estimated value, $/sqft vs ZIP comps, days on market, lot size per dollar
5. **AI memo** on the top N: score 1–10, best strategy, thesis, upside, risks, questions to ask the agent

## Development

```bash
uv pip install -e '.[dev]'
pytest
ruff check src tests
```

## Disclaimer

For personal research. Scraping may be subject to the source sites' terms. Keep volume low and
don't redistribute data. Nothing here is financial advice.

## License

MIT
