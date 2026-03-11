"""
Fiverr Sniper — Selenium-based scraper fallback
================================================
Use this module when Fiverr blocks plain HTTP requests.
Requires Google Chrome + chromedriver (auto-managed via webdriver-manager).

Usage
-----
  from selenium_scraper import scrape_top_gigs_selenium
  gigs = scrape_top_gigs_selenium(query="logo design", min_price=100, max_pages=2)
"""

import logging
import re
import time
import random
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from scraper import (
    GigResult,
    FIVERR_SEARCH_URL,
    CATEGORY_SLUGS,
    _extract_gigs_from_soup,
    _parse_int,
    _parse_float,
    build_search_url,
)

logger = logging.getLogger(__name__)


def _build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _get_page_selenium(driver: webdriver.Chrome, url: str, wait_secs: int = 8) -> Optional[BeautifulSoup]:
    try:
        driver.get(url)
        WebDriverWait(driver, wait_secs).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        # Scroll to trigger lazy-load
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
        time.sleep(1.5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        return BeautifulSoup(driver.page_source, "lxml")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Selenium error fetching %s: %s", url, exc)
        return None


def _scrape_detail_selenium(driver: webdriver.Chrome, gig: GigResult) -> GigResult:
    soup = _get_page_selenium(driver, gig.gig_url)
    if not soup:
        return gig

    for el in soup.find_all(string=re.compile(r"order", re.I)):
        txt = el.strip()
        if "queue" in txt.lower():
            n = _parse_int(txt)
            if n > 0:
                gig.orders_in_queue = max(gig.orders_in_queue, n)

    queue_tags = soup.select("[class*='queue']") + soup.select("[class*='orders-in']")
    for tag in queue_tags:
        n = _parse_int(tag.get_text(strip=True))
        if n > 0:
            gig.orders_in_queue = max(gig.orders_in_queue, n)

    return gig


def scrape_top_gigs_selenium(
    query: str = "web development",
    category: str = "",
    min_price: int = 50,
    max_pages: int = 3,
    top_n: int = 20,
    detail_scrape: bool = True,
    delay: float = 3.0,
    headless: bool = True,
) -> list[GigResult]:
    """
    Selenium version of scrape_top_gigs().
    Use when plain HTTP requests are blocked by Fiverr.
    """
    driver = _build_driver(headless=headless)
    all_gigs: list[GigResult] = []
    seen_urls: set[str] = set()

    try:
        for page in range(1, max_pages + 1):
            url = build_search_url(query=query, category=category, min_price=min_price, page=page)
            logger.info("Selenium fetching page %d: %s", page, url)
            soup = _get_page_selenium(driver, url)
            if not soup:
                logger.warning("Skipping page %d", page)
                continue

            gigs = _extract_gigs_from_soup(soup)
            logger.info("  → Found %d gigs on page %d", len(gigs), page)

            for g in gigs:
                if g.gig_url not in seen_urls:
                    seen_urls.add(g.gig_url)
                    all_gigs.append(g)

            if page < max_pages:
                time.sleep(delay + random.uniform(0.5, 2.0))

        if detail_scrape and all_gigs:
            logger.info("Scraping %d gig detail pages for orders-in-queue…", len(all_gigs))
            for i, gig in enumerate(all_gigs, 1):
                logger.info("  [%d/%d] %s", i, len(all_gigs), gig.gig_url)
                all_gigs[i - 1] = _scrape_detail_selenium(driver, gig)
                time.sleep(delay + random.uniform(0.5, 1.5))

    finally:
        driver.quit()

    all_gigs.sort(key=lambda g: (g.orders_in_queue, g.price), reverse=True)
    return all_gigs[:top_n]
