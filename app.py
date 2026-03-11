"""
Fiverr Sniper — FastAPI Web Application
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import AsyncGenerator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from scraper import CATEGORIES, run_sniper, GigResult, SniperReport

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)

app = FastAPI(title="Fiverr Sniper", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=4)

# ---------------------------------------------------------------------------
# SSE streaming endpoint  —  GET /api/snipe?keyword=...
# The browser opens this as an EventSource; we stream progress + final JSON.
# ---------------------------------------------------------------------------

def _gig_to_dict(g: GigResult) -> dict:
    return {
        "seller":          g.seller,
        "title":           g.title,
        "gig_url":         g.gig_url,
        "price":           g.price,
        "orders_in_queue": g.orders_in_queue,
        "rating":          g.rating,
        "review_count":    g.review_count,
        "seller_level":    g.seller_level,
        "thumbnail":       g.thumbnail,
    }


def _report_to_dict(r: SniperReport) -> dict:
    return {
        "keyword":            r.keyword,
        "competition_count":  r.competition_count,
        "competition_label":  r.competition_label,
        "competition_color":  r.competition_color,
        "sniper_score":       r.sniper_score,
        "sniper_label":       r.sniper_label,
        "total_queue_demand": r.total_queue_demand,
        "avg_orders_in_queue":r.avg_orders_in_queue,
        "gigs":               [_gig_to_dict(g) for g in r.gigs],
    }


async def _stream_snipe(
    keyword: str,
    min_price: int,
    max_pages: int,
    top_n: int,
    detail_scrape: bool,
    delay: float,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def progress_cb(msg: str):
        loop.call_soon_threadsafe(queue.put_nowait, json.dumps({"type": "progress", "message": msg}))

    def run():
        try:
            report = run_sniper(
                keyword=keyword,
                min_price=min_price,
                max_pages=max_pages,
                top_n=top_n,
                detail_scrape=detail_scrape,
                delay=delay,
                progress_cb=progress_cb,
            )
            payload = json.dumps({"type": "result", "data": _report_to_dict(report)})
            loop.call_soon_threadsafe(queue.put_nowait, payload)
        except Exception as e:
            err = json.dumps({"type": "error", "message": str(e)})
            loop.call_soon_threadsafe(queue.put_nowait, err)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, "__DONE__")

    loop.run_in_executor(_executor, run)

    while True:
        item = await queue.get()
        if item == "__DONE__":
            yield "data: {\"type\": \"done\"}\n\n"
            break
        yield f"data: {item}\n\n"
        await asyncio.sleep(0)


@app.get("/api/snipe")
async def snipe(
    keyword:       str   = Query(..., min_length=1),
    min_price:     int   = Query(100,  ge=0),
    max_pages:     int   = Query(3,    ge=1, le=10),
    top_n:         int   = Query(20,   ge=1, le=50),
    detail_scrape: bool  = Query(True),
    delay:         float = Query(2.0,  ge=0.5, le=10.0),
):
    return StreamingResponse(
        _stream_snipe(keyword, min_price, max_pages, top_n, detail_scrape, delay),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/categories")
async def categories():
    return {"categories": list(CATEGORIES.keys())}


# ---------------------------------------------------------------------------
# Serve static front-end
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
