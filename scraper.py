"""
Fiverr Sniper - Core Scraper Module
Scrapes top-paying Fiverr gigs and surfaces sellers with maximum orders in queue.
"""

import time
import re
import random
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
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

    def __repr__(self) -> str:
        return (
            f"GigResult(seller={self.seller!r}, orders_in_queue={self.orders_in_queue}, "
            f"price=${self.price:.2f}, url={self.gig_url!r})"
        )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def _get_page(session: requests.Session, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """Fetch a URL and return parsed HTML, with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "lxml")
            elif resp.status_code == 429:
                wait = 2 ** attempt + random.uniform(1, 3)
                logger.warning("Rate-limited (429). Waiting %.1fs before retry %d/%d", wait, attempt, retries)
                time.sleep(wait)
            elif resp.status_code in (403, 503):
                logger.warning("Blocked (%d) on attempt %d/%d: %s", resp.status_code, attempt, retries, url)
                time.sleep(random.uniform(3, 7))
            else:
                logger.warning("HTTP %d for %s", resp.status_code, url)
                return None
        except requests.RequestException as exc:
            logger.warning("Request error (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_int(text: str) -> int:
    """Extract the first integer from a string, e.g. '12 orders in queue' → 12."""
    m = re.search(r"\d[\d,]*", text.replace(",", ""))
    return int(m.group()) if m else 0


def _parse_float(text: str) -> float:
    m = re.search(r"[\d.]+", text.replace(",", ""))
    return float(m.group()) if m else 0.0


# ---------------------------------------------------------------------------
# Gig-card extraction strategies
# ---------------------------------------------------------------------------

def _extract_gigs_from_soup(soup: BeautifulSoup, base_url: str = "https://www.fiverr.com") -> list[GigResult]:
    """
    Try multiple CSS-selector strategies to extract gig cards from a Fiverr
    search-results page, because Fiverr's markup changes frequently.
    """
    gigs: list[GigResult] = []

    # Strategy A: standard gig cards (class names Fiverr uses)
    cards = (
        soup.select("div.gig-card-layout")
        or soup.select("li[class*='gig-card']")
        or soup.select("div[class*='gig-wrapper']")
        or soup.select("article[class*='gig']")
        or soup.select("div[class*='BasicSellerCard']")
        or soup.select("[data-impressionable='true']")
        or soup.select("li.gig-card")
    )

    if not cards:
        # Strategy B: look for any anchor that links to a /s2.fiverr.com gig path
        logger.debug("No card containers found; falling back to link scan")
        anchors = soup.find_all("a", href=re.compile(r"/[^/]+/[^/]+"))
        seen: set[str] = set()
        for a in anchors:
            href = a.get("href", "")
            if not href.startswith("/") or href.count("/") < 2:
                continue
            full_url = base_url + href if href.startswith("/") else href
            if full_url in seen:
                continue
            seen.add(full_url)
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            gigs.append(
                GigResult(
                    seller="unknown",
                    title=title[:120],
                    gig_url=full_url,
                    price=0.0,
                    orders_in_queue=0,
                )
            )
        return gigs

    for card in cards:
        try:
            gig = _parse_card(card, base_url)
            if gig:
                gigs.append(gig)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Error parsing card: %s", exc)

    return gigs


def _parse_card(card: BeautifulSoup, base_url: str) -> Optional[GigResult]:
    """Parse a single gig card element into a GigResult."""

    # --- Gig URL & Title ---
    link_el = (
        card.select_one("a[href*='/s2.fiverr.com']")
        or card.select_one("a[href*='/gig/']")
        or card.select_one("a.gig-card-layout")
        or card.select_one("a[class*='title']")
        or card.find("a", href=re.compile(r"/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+"))
    )
    if not link_el:
        return None

    href = link_el.get("href", "")
    if href.startswith("//"):
        gig_url = "https:" + href
    elif href.startswith("/"):
        gig_url = base_url + href
    else:
        gig_url = href

    title_el = (
        card.select_one("p[class*='title']")
        or card.select_one("h3")
        or card.select_one("[class*='title']")
        or link_el
    )
    title = title_el.get_text(strip=True) if title_el else "N/A"

    # --- Seller ---
    seller_el = (
        card.select_one("[class*='seller-name']")
        or card.select_one("[class*='username']")
        or card.select_one("a[class*='seller']")
        or card.select_one("[class*='sellerName']")
        or card.select_one("span[class*='level']")
    )
    seller = seller_el.get_text(strip=True) if seller_el else "unknown"
    # Sometimes the seller name is embedded in the gig URL: /username/gig-slug
    if seller == "unknown":
        parts = [p for p in gig_url.split("/") if p and p not in ("www.fiverr.com", "fiverr.com", "https:")]
        if parts:
            seller = parts[0]

    # --- Price ---
    price_el = (
        card.select_one("[class*='price']")
        or card.select_one("span[class*='Price']")
        or card.select_one("[data-price]")
    )
    price = 0.0
    if price_el:
        price = _parse_float(price_el.get_text(strip=True))
    if price == 0.0 and price_el and price_el.get("data-price"):
        price = _parse_float(price_el["data-price"])

    # --- Rating ---
    rating_el = (
        card.select_one("[class*='rating']")
        or card.select_one("[class*='stars']")
        or card.select_one("b[class*='rating']")
    )
    rating: Optional[float] = None
    if rating_el:
        rating = _parse_float(rating_el.get_text(strip=True)) or None

    # --- Review count ---
    review_el = (
        card.select_one("[class*='review']")
        or card.select_one("span[class*='count']")
    )
    review_count = 0
    if review_el:
        review_count = _parse_int(review_el.get_text(strip=True))

    # --- Orders in Queue ---
    orders_in_queue = 0
    # Look for explicit "orders in queue" text anywhere in the card
    for el in card.find_all(string=re.compile(r"order", re.I)):
        txt = el.strip()
        if "queue" in txt.lower() or "order" in txt.lower():
            orders_in_queue = max(orders_in_queue, _parse_int(txt))

    # Also look in elements that commonly hold queue badges
    queue_el = (
        card.select_one("[class*='queue']")
        or card.select_one("[class*='orders']")
        or card.select_one("[class*='busy']")
    )
    if queue_el:
        orders_in_queue = max(orders_in_queue, _parse_int(queue_el.get_text(strip=True)))

    # --- Seller level ---
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
    )


# ---------------------------------------------------------------------------
# Gig-detail page scraper (gets accurate orders_in_queue per gig)
# ---------------------------------------------------------------------------

def _scrape_gig_detail(session: requests.Session, gig: GigResult) -> GigResult:
    """Visit the individual gig page to extract the orders-in-queue count."""
    soup = _get_page(session, gig.gig_url)
    if not soup:
        return gig

    # Patterns found on gig detail pages
    for el in soup.find_all(string=re.compile(r"order", re.I)):
        txt = el.strip()
        if "queue" in txt.lower():
            n = _parse_int(txt)
            if n > 0:
                gig.orders_in_queue = n
                break

    queue_tags = (
        soup.select("[class*='queue']")
        + soup.select("[class*='orders-in']")
        + soup.select("[data-testid*='queue']")
    )
    for tag in queue_tags:
        n = _parse_int(tag.get_text(strip=True))
        if n > 0:
            gig.orders_in_queue = max(gig.orders_in_queue, n)

    # Also try to refresh price from detail page
    price_el = soup.select_one("[class*='price-value']") or soup.select_one("[class*='package-price']")
    if price_el:
        p = _parse_float(price_el.get_text(strip=True))
        if p > 0:
            gig.price = p

    return gig


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

FIVERR_SEARCH_URL = "https://www.fiverr.com/search/gigs"

CATEGORY_SLUGS = {
    "programming": "programming-tech",
    "design": "graphics-design",
    "writing": "writing-translation",
    "video": "video-animation",
    "marketing": "digital-marketing",
    "business": "business",
    "music": "music-audio",
    "ai": "programming-tech/ai-coding",
}


def build_search_url(
    query: str = "",
    category: str = "",
    min_price: int = 100,
    sort: str = "best_selling",
    page: int = 1,
) -> str:
    params: list[str] = []
    if query:
        params.append(f"query={requests.utils.quote(query)}")
    if category:
        slug = CATEGORY_SLUGS.get(category.lower(), category)
        params.append(f"filter=category_id&category_slug={slug}")
    params.append(f"min_price={min_price}")
    params.append(f"sort={sort}")
    if page > 1:
        params.append(f"page={page}")
    return FIVERR_SEARCH_URL + ("?" + "&".join(params) if params else "")


def scrape_top_gigs(
    query: str = "web development",
    category: str = "",
    min_price: int = 50,
    max_pages: int = 3,
    top_n: int = 20,
    detail_scrape: bool = True,
    delay: float = 2.0,
) -> list[GigResult]:
    """
    Scrape Fiverr search results and return the top gigs sorted by
    orders-in-queue (descending).

    Parameters
    ----------
    query        : Search keyword(s)
    category     : Optional category filter (programming, design, writing, …)
    min_price    : Minimum gig price to filter by
    max_pages    : How many search-result pages to crawl
    top_n        : Return only the top N results
    detail_scrape: Visit each gig page to get accurate orders-in-queue counts
    delay        : Polite delay (seconds) between requests
    """
    session = _build_session()
    all_gigs: list[GigResult] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        url = build_search_url(query=query, category=category, min_price=min_price, page=page)
        logger.info("Fetching search page %d: %s", page, url)

        soup = _get_page(session, url)
        if not soup:
            logger.warning("Skipping page %d (failed to fetch)", page)
            continue

        gigs = _extract_gigs_from_soup(soup)
        logger.info("  → Found %d gigs on page %d", len(gigs), page)

        for g in gigs:
            if g.gig_url not in seen_urls:
                seen_urls.add(g.gig_url)
                all_gigs.append(g)

        if page < max_pages:
            time.sleep(delay + random.uniform(0.5, 1.5))

    if not all_gigs:
        logger.warning("No gigs found. Fiverr may be blocking requests or the page structure changed.")
        return []

    # Optionally visit each gig detail page to get accurate orders-in-queue
    if detail_scrape:
        logger.info("Scraping individual gig pages for orders-in-queue data (%d gigs)…", len(all_gigs))
        for i, gig in enumerate(all_gigs, 1):
            logger.info("  [%d/%d] %s", i, len(all_gigs), gig.gig_url)
            all_gigs[i - 1] = _scrape_gig_detail(session, gig)
            time.sleep(delay + random.uniform(0.3, 1.0))

    # Sort by orders_in_queue descending, then by price descending as tie-break
    all_gigs.sort(key=lambda g: (g.orders_in_queue, g.price), reverse=True)

    return all_gigs[:top_n]
