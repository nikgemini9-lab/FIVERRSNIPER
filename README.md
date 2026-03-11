# 🎯 Fiverr Sniper

A market-intelligence **webapp** that scrapes Fiverr for any keyword, calculates
**competition level** (total results count), **orders-in-queue demand**, and
produces a **Sniper Score** — so you can spot low-competition / high-demand
niches before everyone else.

> All results filtered to **$100+ packages only**.

---

## Features

| Feature | Detail |
|---|---|
| Keyword search | Any keyword across all of Fiverr |
| Competition count | Extracts how many total results Fiverr shows |
| Orders in queue | Per-seller queue depth (detail-page scraped) |
| Sniper Score | `demand / competition` composite score 0–100 |
| Opportunity verdict | SNIPER SHOT / GOOD / MODERATE / SATURATED |
| Real-time streaming | SSE progress updates while scraping |
| $100+ filter | Ignores cheap gigs automatically |
| Fiverr-dark UI | Responsive single-page app |

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py          # → http://localhost:8000
```

Or with uvicorn directly:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

---

## Sniper Score Algorithm

```
demand      = total orders-in-queue across top sellers  (capped at 50 = 1.0)
comp_norm   = log10(competition + 1) / log10(100,000)   (0 = 1 result, 1 = 100k+)
sniper_score = demand × (1 − comp_norm) × 100
```

| Score | Verdict |
|---|---|
| ≥ 70 | 🎯 SNIPER SHOT — pull the trigger |
| 45–70 | ✅ GOOD OPPORTUNITY |
| 20–45 | ⚠️ MODERATE |
| < 20 | 🔴 SATURATED — avoid |

---

## Project Structure

```
FIVERRSNIPER/
├── app.py          FastAPI backend + SSE streaming
├── scraper.py      Core HTTP scraper (requests + BeautifulSoup)
├── requirements.txt
├── static/
│   ├── index.html  SPA entry point
│   ├── styles.css  Fiverr dark theme
│   └── app.js      Frontend logic
└── README.md
```

---

## Example Keywords

- `akashic record reading` — spiritual niche, very low competition
- `AI avatar creator` — AI niche, high demand
- `AI voice cloning` — emerging AI service
- `prompt engineering` — hot AI skill
- `AI chatbot development` — high ticket, growing demand

---

## Notes

- Fiverr uses Cloudflare. If you hit 403/429 errors, increase the **delay** slider.
- The detail-scrape toggle visits every gig page for accurate queue counts — slower but more accurate.
- For production, add a proxy rotation layer (e.g. BrightData / ScraperAPI).
