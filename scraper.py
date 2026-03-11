"""
Fiverr Sniper — Core Scraper
Extracts: gig data, orders-in-queue, competition count (total results for keyword).
All gigs are filtered to $100+ base price.
"""

import logging
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import os

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Set SCRAPERAPI_KEY env var to route all requests through ScraperAPI.
# Avoids datacenter IP blocks when running on cloud hosts (Render, Railway…).
# Free tier: 1,000 req/month — https://www.scraperapi.com
_SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "").strip()


def _scraper_url(url: str) -> str:
    """Wrap a URL with ScraperAPI proxy if key is configured."""
    if _SCRAPERAPI_KEY:
        encoded = requests.utils.quote(url, safe="")
        return f"http://api.scraperapi.com/?api_key={_SCRAPERAPI_KEY}&url={encoded}&render=false"
    return url

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GigResult:
    seller: str
    title: str
    gig_url: str
    price: float
    orders_in_queue: int
    rating: Optional[float] = None
    review_count: int = 0
    seller_level: str = ""
    thumbnail: str = ""


@dataclass
class SniperReport:
    keyword: str
    competition_count: int          # total results Fiverr reports for keyword
    competition_label: str          # LOW / MEDIUM / HIGH / SATURATED
    competition_color: str          # green / yellow / orange / red
    sniper_score: float             # 0–100
    sniper_label: str               # SNIPER SHOT / GOOD OPPORTUNITY / etc.
    total_queue_demand: int         # sum of orders in queue across top sellers
    avg_orders_in_queue: float
    gigs: list[GigResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Broad category map — every major Fiverr vertical including AI
# ---------------------------------------------------------------------------

CATEGORIES = {
    # AI / Tech
    "ai_services":          "programming-tech/ai-coding",
    "ai_chatbots":          "programming-tech/chatbots",
    "machine_learning":     "programming-tech/machine-learning",
    "data_science":         "programming-tech/data-science",
    "web_development":      "programming-tech/web-programming",
    "mobile_apps":          "programming-tech/mobile-apps",
    "automation":           "programming-tech/scripts-plugins",
    "blockchain":           "programming-tech/blockchain-nft",
    # Creative
    "graphics_design":      "graphics-design",
    "video_animation":      "video-animation",
    "music_audio":          "music-audio",
    # Business / Finance
    "business":             "business",
    "finance":              "finance",
    "consulting":           "business/consulting",
    # Writing / Content
    "writing":              "writing-translation",
    "seo":                  "digital-marketing/search-engine-optimization",
    "digital_marketing":    "digital-marketing",
    # Lifestyle / Spiritual (niche = low competition gems)
    "spiritual":            "lifestyle/spiritual-wellness-psychics",
    "lifestyle":            "lifestyle",
    "online_tutoring":      "online-tutoring",
}

FIVERR_BASE = "https://www.fiverr.com"
SEARCH_URL  = f"{FIVERR_BASE}/search/gigs"

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
    })
    return s


def _fetch(session: requests.Session, url: str, retries: int = 4) -> Optional[BeautifulSoup]:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(_scraper_url(url), timeout=60)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            if r.status_code == 429:
                wait = 2 ** attempt + random.uniform(1, 3)
                logger.warning("Rate-limited. Waiting %.1fs (attempt %d/%d)", wait, attempt, retries)
                time.sleep(wait)
            elif r.status_code in (403, 503):
                logger.warning("Blocked (%s) on attempt %d: %s", r.status_code, attempt, url)
                time.sleep(random.uniform(4, 8))
            else:
                logger.warning("HTTP %s for %s", r.status_code, url)
                return None
        except requests.RequestException as e:
            logger.warning("Request error attempt %d: %s", attempt, e)
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _int(text: str) -> int:
    m = re.search(r"[\d,]+", text)
    return int(m.group().replace(",", "")) if m else 0


def _float(text: str) -> float:
    m = re.search(r"[\d.]+", text.replace(",", ""))
    return float(m.group()) if m else 0.0


def _parse_competition(soup: BeautifulSoup) -> int:
    """
    Extract the total result count Fiverr displays for a search query.
    e.g. "600 services available" or "23,479 results"
    """
    # Strategy 1: look for heading/paragraph with count
    for selector in [
        "[class*='sub-title']",
        "[class*='results-count']",
        "[class*='search-results'] h1",
        "[class*='count']",
        "h1",
        "h2",
        "[class*='title']",
    ]:
        els = soup.select(selector)
        for el in els:
            txt = el.get_text(strip=True)
            # "600 services" / "23,479 results" / "I found 600..."
            m = re.search(r"([\d,]+)\s*(services|results|gigs|sellers)", txt, re.I)
            if m:
                return int(m.group(1).replace(",", ""))

    # Strategy 2: scan all text nodes
    for el in soup.find_all(string=re.compile(r"\d[\d,]*\s*(services|results|gigs)", re.I)):
        m = re.search(r"([\d,]+)\s*(services|results|gigs)", el, re.I)
        if m:
            return int(m.group(1).replace(",", ""))

    return 0


def _competition_meta(count: int) -> tuple[str, str]:
    """Returns (label, colour)."""
    if count == 0:
        return "UNKNOWN", "gray"
    if count < 500:
        return "ULTRA LOW", "emerald"
    if count < 2_000:
        return "LOW", "green"
    if count < 10_000:
        return "MEDIUM", "yellow"
    if count < 50_000:
        return "HIGH", "orange"
    return "SATURATED", "red"


def _sniper_score(competition: int, total_queue: int) -> tuple[float, str]:
    """
    Score 0–100.
    High demand (total orders in queue) + low competition = high score.
    """
    if competition <= 0:
        competition = 1
    demand = min(1.0, total_queue / 50.0)
    # normalise competition on log10 scale (1 → 0, 100k+ → 1)
    comp_norm = min(1.0, math.log10(competition + 1) / math.log10(100_000))
    raw = demand * (1.0 - comp_norm) * 100
    score = round(min(100.0, raw), 1)

    if score >= 70:
        label = "SNIPER SHOT 🎯"
    elif score >= 45:
        label = "GOOD OPPORTUNITY"
    elif score >= 20:
        label = "MODERATE"
    else:
        label = "SATURATED"
    return score, label


# ---------------------------------------------------------------------------
# Gig extraction
# ---------------------------------------------------------------------------

def _parse_gig_card(card, base: str = FIVERR_BASE) -> Optional[GigResult]:
    # Link
    link = (
        card.select_one("a[href*='/s2.fiverr.com']")
        or card.select_one("a[href*='/gig/']")
        or card.find("a", href=re.compile(r"/[a-zA-Z0-9_%-]+/[a-zA-Z0-9_%-]+"))
    )
    if not link:
        return None
    href = link.get("href", "")
    gig_url = ("https:" + href) if href.startswith("//") else (base + href if href.startswith("/") else href)

    # Seller from URL path
    parts = [p for p in gig_url.replace("https://www.fiverr.com/", "").split("/") if p]
    seller = parts[0] if parts else "unknown"

    # Title
    title_el = (
        card.select_one("p[class*='title']")
        or card.select_one("h3")
        or card.select_one("[class*='title']")
        or link
    )
    title = title_el.get_text(strip=True) if title_el else "N/A"

    # Override seller from dedicated element if present
    sel_el = (
        card.select_one("[class*='seller-name']")
        or card.select_one("[class*='username']")
        or card.select_one("[class*='sellerName']")
    )
    if sel_el:
        seller = sel_el.get_text(strip=True) or seller

    # Price — grab the highest visible price (package price)
    price = 0.0
    for p_el in card.select("[class*='price']") + card.select("[class*='Price']"):
        txt = p_el.get_text(strip=True)
        candidate = _float(txt)
        if candidate > price:
            price = candidate

    # Rating
    rating_el = card.select_one("[class*='rating']") or card.select_one("b[class*='rating']")
    rating = _float(rating_el.get_text()) if rating_el else None
    if rating and (rating > 5 or rating < 1):
        rating = None

    # Review count
    rev_el = card.select_one("[class*='review']") or card.select_one("span[class*='count']")
    review_count = _int(rev_el.get_text()) if rev_el else 0

    # Orders in queue
    orders_in_queue = 0
    for txt_node in card.find_all(string=re.compile(r"order|queue", re.I)):
        n = _int(str(txt_node))
        if n > orders_in_queue:
            orders_in_queue = n
    for sel in ["[class*='queue']", "[class*='orders']", "[class*='busy']"]:
        for el in card.select(sel):
            n = _int(el.get_text())
            if n > orders_in_queue:
                orders_in_queue = n

    # Thumbnail
    img = card.select_one("img[src]") or card.select_one("img[data-src]")
    thumbnail = ""
    if img:
        thumbnail = img.get("src") or img.get("data-src", "")
        if thumbnail.startswith("//"):
            thumbnail = "https:" + thumbnail

    # Seller level badge
    level_el = card.select_one("[class*='level']") or card.select_one("[class*='badge']")
    seller_level = level_el.get_text(strip=True) if level_el else ""

    return GigResult(
        seller=seller,
        title=title[:120],
        gig_url=gig_url,
        price=price,
        orders_in_queue=orders_in_queue,
        rating=rating,
        review_count=review_count,
        seller_level=seller_level,
        thumbnail=thumbnail,
    )


def _extract_gigs(soup: BeautifulSoup) -> list[GigResult]:
    cards = (
        soup.select("div.gig-card-layout")
        or soup.select("li[class*='gig-card']")
        or soup.select("div[class*='gig-wrapper']")
        or soup.select("article[class*='gig']")
        or soup.select("[data-impressionable='true']")
        or soup.select("li.gig-card")
    )
    gigs = []
    for card in cards:
        try:
            g = _parse_gig_card(card)
            if g:
                gigs.append(g)
        except Exception:
            pass
    return gigs


def _enrich_from_detail(session: requests.Session, gig: GigResult) -> GigResult:
    """Visit gig page to get accurate orders-in-queue and max package price."""
    soup = _fetch(session, gig.gig_url)
    if not soup:
        return gig

    # Orders in queue
    for txt_node in soup.find_all(string=re.compile(r"order", re.I)):
        txt = str(txt_node).strip()
        if "queue" in txt.lower():
            n = _int(txt)
            if n > 0:
                gig.orders_in_queue = max(gig.orders_in_queue, n)
    for sel in ["[class*='queue']", "[class*='orders-in']", "[data-testid*='queue']"]:
        for el in soup.select(sel):
            n = _int(el.get_text())
            if n > 0:
                gig.orders_in_queue = max(gig.orders_in_queue, n)

    # Highest package price on detail page
    max_price = gig.price
    for el in soup.select("[class*='price']") + soup.select("[class*='package']"):
        candidate = _float(el.get_text())
        if candidate > max_price:
            max_price = candidate
    gig.price = max_price

    return gig


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_url(keyword: str, min_price: int = 100, sort: str = "best_selling", page: int = 1) -> str:
    q = requests.utils.quote(keyword.strip())
    url = f"{SEARCH_URL}?query={q}&sort={sort}&min_price={min_price}"
    if page > 1:
        url += f"&page={page}"
    return url


def run_sniper(
    keyword: str,
    min_price: int = 100,
    max_pages: int = 3,
    top_n: int = 20,
    detail_scrape: bool = True,
    delay: float = 2.0,
    progress_cb=None,          # callable(message: str) for SSE streaming
) -> SniperReport:
    """
    Main entry point.

    Parameters
    ----------
    keyword      : Fiverr search keyword
    min_price    : Minimum package price (default $100)
    max_pages    : Search pages to crawl
    top_n        : Return top N gigs
    detail_scrape: Visit each gig page for accurate queue counts
    delay        : Polite delay between requests
    progress_cb  : Optional callback to stream progress updates
    """
    def emit(msg: str):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    session = _session()
    all_gigs: list[GigResult] = []
    seen: set[str] = set()
    competition_count = 0

    for page in range(1, max_pages + 1):
        url = build_url(keyword, min_price=min_price, page=page)
        emit(f"Fetching search page {page}/{max_pages}…")
        soup = _fetch(session, url)
        if not soup:
            emit(f"⚠️ Page {page} failed to load — skipping")
            continue

        if page == 1:
            competition_count = _parse_competition(soup)
            emit(f"Competition: {competition_count:,} results found for '{keyword}'")

        gigs = _extract_gigs(soup)
        emit(f"Found {len(gigs)} gigs on page {page}")

        for g in gigs:
            if g.gig_url not in seen and g.price >= min_price:
                seen.add(g.gig_url)
                all_gigs.append(g)

        if page < max_pages:
            time.sleep(delay + random.uniform(0.5, 1.5))

    if not all_gigs:
        emit("⚠️ No gigs found — Fiverr may be blocking requests. Try increasing delay or use Selenium mode.")

    # Detail scraping for accurate queue counts
    if detail_scrape and all_gigs:
        emit(f"Scraping {len(all_gigs)} gig detail pages…")
        for i, gig in enumerate(all_gigs, 1):
            emit(f"Detail [{i}/{len(all_gigs)}]: {gig.seller}")
            all_gigs[i - 1] = _enrich_from_detail(session, gig)
            time.sleep(delay + random.uniform(0.3, 1.0))

    # Filter: only $100+
    all_gigs = [g for g in all_gigs if g.price >= min_price]

    # Sort by orders in queue desc, then price desc
    all_gigs.sort(key=lambda g: (g.orders_in_queue, g.price), reverse=True)
    top_gigs = all_gigs[:top_n]

    total_queue = sum(g.orders_in_queue for g in top_gigs)
    avg_queue = round(total_queue / len(top_gigs), 1) if top_gigs else 0

    comp_label, comp_color = _competition_meta(competition_count)
    score, score_label = _sniper_score(competition_count, total_queue)

    emit(f"✅ Done — Sniper Score: {score} ({score_label})")

    return SniperReport(
        keyword=keyword,
        competition_count=competition_count,
        competition_label=comp_label,
        competition_color=comp_color,
        sniper_score=score,
        sniper_label=score_label,
        total_queue_demand=total_queue,
        avg_orders_in_queue=avg_queue,
        gigs=top_gigs,
    )
