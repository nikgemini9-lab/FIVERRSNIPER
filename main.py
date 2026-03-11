#!/usr/bin/env python3
"""
Fiverr Sniper — CLI entry point
================================
Find sellers with the highest orders-in-queue on top-paying Fiverr gigs.

Usage examples
--------------
  python main.py
  python main.py --query "logo design" --min-price 50 --pages 5 --top 15
  python main.py --query "python bot" --category programming --min-price 200
  python main.py --query "video editing" --no-detail --export results.json
"""

import argparse
import json
import sys
import time
from datetime import datetime

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text

from scraper import GigResult, CATEGORY_SLUGS, scrape_top_gigs

console = Console()

BANNER = r"""
  _____ _                 ____        _
 |  ___(_)_   _____ _ __|  _ \ ___  (_)_ __   ___ _ __
 | |_  | \ \ / / _ \ '__| |_) / __| | | '_ \ / _ \ '__|
 |  _| | |\ V /  __/ |  |  _ <\__ \ | | |_) |  __/ |
 |_|   |_| \_/ \___|_|  |_| \_\___/ |_| .__/ \___|_|
                                        |_|
         S N I P E R   —   Top Gig Queue Tracker
"""


def build_table(gigs: list[GigResult]) -> Table:
    table = Table(
        title="[bold magenta]Top Fiverr Gigs by Orders in Queue[/bold magenta]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        expand=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Seller", style="bold green", min_width=16)
    table.add_column("Gig Title", min_width=30)
    table.add_column("Price", style="yellow", justify="right", width=10)
    table.add_column("Orders in Queue", style="bold red", justify="center", width=16)
    table.add_column("Rating", justify="center", width=10)
    table.add_column("Gig URL", style="blue", min_width=40)

    for rank, gig in enumerate(gigs, 1):
        queue_text = (
            Text(str(gig.orders_in_queue), style="bold red")
            if gig.orders_in_queue > 0
            else Text("—", style="dim")
        )
        rating_text = (
            f"⭐ {gig.rating:.1f} ({gig.review_count:,})"
            if gig.rating
            else "—"
        )
        price_text = f"${gig.price:.0f}" if gig.price > 0 else "—"
        table.add_row(
            str(rank),
            gig.seller,
            gig.title[:60] + ("…" if len(gig.title) > 60 else ""),
            price_text,
            queue_text,
            rating_text,
            gig.gig_url,
        )

    return table


def export_json(gigs: list[GigResult], path: str) -> None:
    data = []
    for g in gigs:
        data.append(
            {
                "seller": g.seller,
                "title": g.title,
                "gig_url": g.gig_url,
                "price_usd": g.price,
                "orders_in_queue": g.orders_in_queue,
                "rating": g.rating,
                "review_count": g.review_count,
                "seller_level": g.seller_level,
            }
        )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"scraped_at": datetime.utcnow().isoformat() + "Z", "results": data},
            f,
            indent=2,
            ensure_ascii=False,
        )
    console.print(f"[green]Results exported to[/green] [bold]{path}[/bold]")


def print_summary(gigs: list[GigResult]) -> None:
    if not gigs:
        return
    with_queue = [g for g in gigs if g.orders_in_queue > 0]
    top = gigs[0] if gigs else None

    console.print(
        Panel(
            f"[bold]Total gigs analysed:[/bold] {len(gigs)}\n"
            f"[bold]Gigs with orders in queue:[/bold] {len(with_queue)}\n"
            + (
                f"[bold]Top seller:[/bold] [green]{top.seller}[/green]  "
                f"[bold]Orders:[/bold] [red]{top.orders_in_queue}[/red]  "
                f"[bold]Gig:[/bold] {top.gig_url}"
                if top
                else ""
            ),
            title="[bold cyan]Summary[/bold cyan]",
            border_style="cyan",
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fiverr Sniper — Find sellers with the most orders in queue on top-paying gigs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--query", "-q",
        default="web development",
        help="Search keyword(s) [default: 'web development']",
    )
    parser.add_argument(
        "--category", "-c",
        default="",
        choices=[""] + list(CATEGORY_SLUGS.keys()),
        help="Optional Fiverr category filter",
    )
    parser.add_argument(
        "--min-price", "-p",
        type=int,
        default=50,
        dest="min_price",
        help="Minimum gig price (USD) [default: 50]",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Number of search-result pages to crawl [default: 3]",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="How many top results to display [default: 20]",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Polite delay in seconds between HTTP requests [default: 2.0]",
    )
    parser.add_argument(
        "--no-detail",
        action="store_true",
        dest="no_detail",
        help="Skip scraping individual gig pages (faster, less accurate queue counts)",
    )
    parser.add_argument(
        "--export",
        default="",
        metavar="FILE.json",
        help="Export results to a JSON file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    console.print(BANNER, style="bold cyan")
    console.print(
        Panel(
            f"[bold]Query:[/bold] {args.query}\n"
            f"[bold]Category:[/bold] {args.category or 'all'}\n"
            f"[bold]Min price:[/bold] ${args.min_price}\n"
            f"[bold]Pages to crawl:[/bold] {args.pages}\n"
            f"[bold]Detail scrape:[/bold] {'No' if args.no_detail else 'Yes'}\n"
            f"[bold]Top results:[/bold] {args.top}",
            title="[bold yellow]Configuration[/bold yellow]",
            border_style="yellow",
        )
    )

    start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scraping Fiverr…", total=None)

        gigs = scrape_top_gigs(
            query=args.query,
            category=args.category,
            min_price=args.min_price,
            max_pages=args.pages,
            top_n=args.top,
            detail_scrape=not args.no_detail,
            delay=args.delay,
        )
        progress.update(task, completed=100, total=100)

    elapsed = time.time() - start
    console.print(f"\n[dim]Scrape completed in {elapsed:.1f}s[/dim]\n")

    if not gigs:
        console.print(
            "[bold red]No gigs found.[/bold red] "
            "Fiverr may be rate-limiting requests. "
            "Try again in a few minutes or increase --delay."
        )
        sys.exit(1)

    console.print(build_table(gigs))
    print_summary(gigs)

    if args.export:
        export_json(gigs, args.export)


if __name__ == "__main__":
    main()
