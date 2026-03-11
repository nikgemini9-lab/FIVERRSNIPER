# Fiverr Sniper

**Fiverr Sniper** scrapes Fiverr search results for top-paying gigs and surfaces the sellers who have the **maximum number of orders in queue** — the clearest signal of demand and trustworthiness on the platform.

---

## Features

| Feature | Detail |
|---|---|
| Multi-page search crawl | Crawls 1–N search-result pages |
| Price filter | Filter by minimum price (e.g. `--min-price 200`) |
| Category filter | programming, design, writing, video, marketing… |
| Detail-page scraping | Visits every gig page for accurate `orders in queue` count |
| Selenium fallback | `selenium_scraper.py` for when plain HTTP gets blocked |
| Rich table output | Colour-coded terminal table with rank, seller, price, queue, rating |
| JSON export | `--export results.json` for downstream analysis |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

```bash
# Default: search "web development", min price $50, 3 pages, top 20
python main.py

# Custom query
python main.py --query "logo design" --min-price 100 --pages 5 --top 15

# Filter by category
python main.py --query "python bot" --category programming --min-price 200

# Fast mode (skip individual gig pages — less accurate queue counts)
python main.py --query "video editing" --no-detail

# Export to JSON
python main.py --query "SEO" --export seo_gigs.json
```

### 3. Selenium fallback (when Fiverr blocks requests)

```python
from selenium_scraper import scrape_top_gigs_selenium

gigs = scrape_top_gigs_selenium(
    query="logo design",
    min_price=100,
    max_pages=2,
    top_n=10,
)
for g in gigs:
    print(g.seller, g.orders_in_queue, g.gig_url)
```

---

## CLI Options

```
usage: main.py [-h] [--query QUERY] [--category {programming,design,...}]
               [--min-price MIN_PRICE] [--pages PAGES] [--top TOP]
               [--delay DELAY] [--no-detail] [--export FILE.json]

  -q, --query       Search keyword(s)                   [default: web development]
  -c, --category    Category filter                     [default: all]
  -p, --min-price   Minimum gig price (USD)             [default: 50]
      --pages       Search-result pages to crawl        [default: 3]
      --top         Number of top results to show       [default: 20]
      --delay       Seconds between HTTP requests       [default: 2.0]
      --no-detail   Skip individual gig detail pages
      --export      Write results to JSON file
```

---

## Output

The tool prints a ranked table like:

```
╭─────────────────────────────────────────────────────────────────╮
│         Top Fiverr Gigs by Orders in Queue                      │
├──┬──────────────┬────────────────────────┬───────┬─────────┬────┤
│ # │ Seller       │ Gig Title              │ Price │ Queue   │ ⭐ │
├──┼──────────────┼────────────────────────┼───────┼─────────┼────┤
│ 1 │ bestseller99 │ I will build your app  │ $500  │   47    │4.9 │
│ 2 │ designpro    │ I will design your logo│ $250  │   31    │4.8 │
...
```

---

## How It Works

1. **Search scrape** — Fetches Fiverr search results pages using `requests` + `BeautifulSoup`.
2. **Detail scrape** — Visits each gig page to read the accurate `X orders in queue` badge.
3. **Sort & rank** — Sorts all collected gigs by `orders_in_queue` descending (price as tie-break).
4. **Display** — Renders a rich terminal table and (optionally) exports to JSON.

### Note on Fiverr's Anti-Bot Measures

Fiverr uses Cloudflare and JavaScript rendering. If you hit 403/429 errors:
- Increase `--delay` (e.g. `--delay 5`)
- Use the Selenium fallback (`selenium_scraper.py`)
- Run from a residential IP / VPN

---

## Project Structure

```
FIVERRSNIPER/
├── main.py              # CLI entry point (Rich UI)
├── scraper.py           # Core HTTP scraper + data model
├── selenium_scraper.py  # Selenium fallback scraper
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Legal / Ethical Notice

This tool is for **research and competitive intelligence** only. Always respect Fiverr's [Terms of Service](https://www.fiverr.com/terms_of_service) and `robots.txt`. Do not hammer their servers — use polite delays.
