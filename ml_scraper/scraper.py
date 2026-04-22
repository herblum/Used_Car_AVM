#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  scraper.py — MercadoLibre car listing scraper
#
#  Usage:
#    python scraper.py                              # 10-row pilot (default)
#    python scraper.py --rows 100                   # 100-row run
#    python scraper.py --rows 50000 \
#      --batch-size 50 --output data/full.csv       # large run
#    python scraper.py --rows 20 --skip-phase1      # use pre-seeded item_urls.txt
#    python scraper.py --rows 100 --concurrency 5   # 5 parallel browsers
# ─────────────────────────────────────────────
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import config
import parser as item_parser

# ── Optional: rich progress bar ───────────────
try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False
    def tqdm(iterable, **kwargs):  # type: ignore[misc]
        return iterable

# ── Logging ───────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")

# ── Markdown cleaner ──────────────────────────
# Sections confirmed useless for AVM features. Stripped from raw markdown
# after scraping so they don't pollute raw files or confuse the parser.
_STRIP_SECTIONS = re.compile(
    r"^##\s+("
    r"Precios de referencia"
    r"|Información de la (?:tienda|concesionaria)"
    r"|Consejos de seguridad"
    r"|Contactá al (?:particular|vendedor|concesionario)"
    r"|Más publicaciones del vendedor"
    r"|Más información"
    r"|Estamos calculando tus envíos.*"
    r").*",
    re.IGNORECASE,
)

def _clean_markdown(md: str) -> str:
    """
    Strip known-useless sections from a scraped item page.
    Each unwanted '## Section' heading and everything until the next '## '
    heading (or end of string) is removed.
    """
    lines = md.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            skip = bool(_STRIP_SECTIONS.match(stripped))
        if not skip:
            out.append(line)
    return "".join(out)


# ── URL patterns ──────────────────────────────
ITEM_URL_RE = re.compile(
    r"https?://auto\.mercadolibre\.com\.ar/MLA-\d+[^\s\)\"\'\>]*",
    re.IGNORECASE,
)
ITEM_URL_FALLBACK_RE = re.compile(
    r"https?://[a-z]+\.mercadolibre\.com\.ar/MLA-\d+[^\s\)\"\'\>]*",
    re.IGNORECASE,
)


# ── Firecrawl client ──────────────────────────
def _get_client():
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        raise SystemExit(
            "firecrawl-py not installed. Run: pip install -r requirements.txt"
        )
    if config.FIRECRAWL_API_KEY == "fc-YOUR_KEY_HERE":
        raise SystemExit(
            "Set your Firecrawl API key in config.py or via the "
            "FIRECRAWL_API_KEY environment variable."
        )
    return FirecrawlApp(api_key=config.FIRECRAWL_API_KEY)


# ── Pacing helpers ────────────────────────────

def _sleep(min_s: float, max_s: float) -> None:
    t = random.uniform(min_s, max_s)
    log.debug("Sleeping %.1fs", t)
    time.sleep(t)

def _item_sleep() -> None:
    _sleep(config.SLEEP_MIN_S, config.SLEEP_MAX_S)

def _batch_sleep() -> None:
    t = random.uniform(config.BATCH_SLEEP_MIN, config.BATCH_SLEEP_MAX)
    log.info("  Batch pause: %.1fs", t)
    time.sleep(t)

def _listing_sleep() -> None:
    _sleep(config.LISTING_SLEEP_MIN, config.LISTING_SLEEP_MAX)


# ── Scrape with retry ─────────────────────────

def scrape_url(client, url: str, params: dict, label: str = "") -> Optional[str]:
    """
    Attempt to scrape `url` up to MAX_RETRIES times.
    Returns the markdown string, or None if all attempts fail.
    firecrawl-py v4+: app.scrape(url, **snake_case_kwargs) → Document
    """
    for attempt in range(config.MAX_RETRIES):
        try:
            result = client.scrape(url, **params)
            md = result.markdown
            if md and len(md.strip()) > 100:
                return md
            log.warning("%s: empty or too-short response (attempt %d)", label or url, attempt + 1)
        except Exception as exc:
            backoff = config.RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 2)
            log.warning(
                "%s: error on attempt %d/%d — %s. Retrying in %.1fs",
                label or url, attempt + 1, config.MAX_RETRIES, exc, backoff,
            )
            time.sleep(backoff)
    log.error("%s: all %d retries exhausted", label or url, config.MAX_RETRIES)
    return None


# ── Phase 1: Collect item URLs ────────────────

def _listing_page_url(base: str, page: int) -> str:
    """
    MercadoLibre listing pagination:
      page 1 → base URL
      page N → base_Desde_{(N-1)*48+1}_NoIndex_True
    """
    if page == 1:
        return base
    offset = (page - 1) * config.ITEMS_PER_PAGE + 1
    return f"{base}_Desde_{offset}_NoIndex_True"


def _scrape_filter_worker(
    client,
    base_url: str,
    stop_event: "threading.Event",
    lock: "threading.Lock",
    seen_set: set,
    result_list: list,
    urls_needed: int,
) -> None:
    """
    Thread worker for Phase 1: scrapes one filter URL sequentially
    (page 1 → MAX_PAGES_PER_FILTER) until the filter runs dry or the
    shared stop_event signals that enough URLs have been collected.
    """
    import threading  # already imported at module level via ThreadPoolExecutor
    label = base_url.split("/")[-1] or base_url.split("_")[-1]
    consecutive_empty = 0

    for page in range(1, config.MAX_PAGES_PER_FILTER + 1):
        if stop_event.is_set():
            log.info("  [%s] stop signal — halting", label)
            break

        url = _listing_page_url(base_url, page)
        log.info("  [%s] page %d", label, page)
        md = scrape_url(client, url, config.LISTING_PARAMS,
                        label=f"{label}-p{page}")

        if md:
            found = ITEM_URL_RE.findall(md)
            if not found:
                found = ITEM_URL_FALLBACK_RE.findall(md)
            found = [u.split("?")[0].split("#")[0].rstrip("\\") for u in found]
            found = list(dict.fromkeys(found))

            with lock:
                fresh = [u for u in found if u not in seen_set]
                seen_set.update(fresh)
                result_list.extend(fresh)
                total = len(result_list)
                log.info("  [%s] page %d → %d new URLs (%d total)",
                         label, page, len(fresh), total)
                if total >= urls_needed:
                    stop_event.set()

            consecutive_empty = 0 if found else consecutive_empty + 1
            if consecutive_empty >= 2:
                log.info("  [%s] 2 empty pages — filter exhausted", label)
                break
        else:
            log.warning("  [%s] no content on page %d — skipping filter", label, page)
            break

        if page < config.MAX_PAGES_PER_FILTER and not stop_event.is_set():
            _listing_sleep()


def collect_item_urls(
    client,
    urls_needed: int,
    existing: set[str],
    concurrency: int = 8,
) -> list[str]:
    """
    Scrape multiple province filters in parallel (up to `concurrency` at a time).
    Within each filter pages are sequential; filters run concurrently.
    Stops all workers as soon as urls_needed new URLs are collected.
    Returns only URLs not already in `existing`.
    """
    import threading

    stop_event = threading.Event()
    lock       = threading.Lock()
    seen_set   = set(existing)
    result_list: list[str] = []

    n_workers = min(concurrency, len(config.LISTING_URLS))
    log.info(
        "Phase 1 — %d filter(s) in parallel, need %d new URLs",
        n_workers, urls_needed,
    )

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _scrape_filter_worker,
                client, base_url, stop_event, lock,
                seen_set, result_list, urls_needed,
            ): base_url
            for base_url in config.LISTING_URLS
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                log.error("Filter worker error (%s): %s", futures[future], exc)

    log.info("Phase 1 complete — %d new unique URLs collected", len(result_list))
    return result_list


# ── Phase 2: Scrape item pages ────────────────

def _scrape_one_item(client, url: str, label: str) -> tuple[str, Optional[str]]:
    """
    Thread worker: scrape, clean, and save one item page.
    Returns (url, markdown) — markdown is None on failure.
    """
    md = scrape_url(client, url, config.ITEM_PARAMS, label=label)
    if md:
        md = _clean_markdown(md)
        raw_path = Path(config.RAW_DIR) / f"{label}.md"
        raw_path.write_text(md, encoding="utf-8")
    return url, md


def scrape_items(
    client,
    urls: list[str],
    output_csv: str,
    batch_size: int,
    concurrency: int = 50,
) -> int:
    """
    Scrape item URLs in parallel (up to `concurrency` at a time), parse
    features, and write rows to CSV incrementally.
    Returns the number of successfully scraped rows.
    """
    Path(config.RAW_DIR).mkdir(parents=True, exist_ok=True)

    # Global registry of successfully written URLs — shared across all runs
    # and output files. Only URLs that produced a CSV row are recorded here,
    # so failed/blocked URLs are always retried on the next run.
    scraped_path = Path(config.SCRAPED_URLS_FILE)
    scraped: set[str] = set()
    if scraped_path.exists():
        try:
            scraped = set(json.loads(scraped_path.read_text()))
            log.info("Global registry: %d URLs already scraped, skipping", len(scraped))
        except json.JSONDecodeError:
            log.warning("scraped_urls.json corrupt, starting fresh")
    output_path = Path(output_csv)

    pending = [u for u in urls if u not in scraped]
    log.info(
        "Phase 2 — %d items to scrape (concurrency=%d, batch_size=%d)",
        len(pending), concurrency, batch_size,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    import csv as csv_mod
    file_exists = output_path.exists() and output_path.stat().st_size > 0
    success_count = 0
    writer = None

    # Split pending into chunks of `concurrency`; each chunk fires in parallel
    chunks = [pending[i:i + concurrency] for i in range(0, len(pending), concurrency)]
    # How many chunks between long batch pauses
    chunks_per_batch = max(1, batch_size // concurrency)

    try:
        csv_file = open(output_path, "a", newline="", encoding="utf-8")

        # Single pool reused across all chunks — avoids per-chunk thread creation overhead
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for chunk_num, chunk in enumerate(
                tqdm(chunks, desc="Scraping", unit="chunk",
                     bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} chunks [{elapsed}<{remaining}]")
            ):
                global_base = chunk_num * concurrency

                # Submit all URLs in this chunk; pool keeps threads warm between chunks
                future_to_meta = {
                    pool.submit(
                        _scrape_one_item, client, url,
                        f"item-{global_base + i + 1:04d}"
                    ): (url, f"item-{global_base + i + 1:04d}")
                    for i, url in enumerate(chunk)
                }
                chunk_results: list[tuple[str, str, Optional[str]]] = []
                for future in as_completed(future_to_meta):
                    url, label = future_to_meta[future]
                    try:
                        _, md = future.result()
                    except Exception as exc:
                        log.error("%s: unexpected error — %s", label, exc)
                        md = None
                    chunk_results.append((url, label, md))

                # Process results in main thread — no locking required
                for url, label, md in chunk_results:
                    if not md:
                        log.warning("  %s: skipped (no content)", label)
                        continue

                    row = item_parser.extract_features(md, source_url=url)

                    # Defense-in-depth: skip 0km cars
                    km = row.get("kilometros")
                    if km is not None and km == 0:
                        log.warning("  %s: skipped — km=0 (new car)", label)
                        continue

                    if writer is None:
                        writer = csv_mod.DictWriter(csv_file, fieldnames=list(row.keys()))
                        if not file_exists:
                            writer.writeheader()

                    writer.writerow(row)
                    csv_file.flush()
                    success_count += 1
                    # Only register as scraped after a successful CSV write
                    scraped.add(url)
                    log.info(
                        "  ✓ %s  marca=%s modelo=%s anio=%s precio=%s %s",
                        label,
                        row.get("marca") or "?",
                        row.get("modelo") or "?",
                        row.get("anio") or "?",
                        row.get("precio") or "?",
                        row.get("moneda") or "",
                    )

                # Persist global registry after every chunk
                scraped_path.write_text(json.dumps(list(scraped)))

                # Pacing — skip after the very last chunk
                is_last = chunk_num == len(chunks) - 1
                if not is_last:
                    if (chunk_num + 1) % chunks_per_batch == 0:
                        log.info(
                            "  --- Batch %d complete (%d items done) ---",
                            (chunk_num + 1) // chunks_per_batch,
                            (chunk_num + 1) * concurrency,
                        )
                        _batch_sleep()
                    else:
                        _item_sleep()

    finally:
        if csv_file:
            csv_file.close()

    return success_count


# ── Coverage report ───────────────────────────

def print_coverage(output_csv: str) -> None:
    try:
        import pandas as pd
    except ImportError:
        log.info("pandas not installed — skipping coverage report")
        return

    df = pd.read_csv(output_csv)
    print("\n── Coverage report ─────────────────────────")
    coverage = (df.notnull().mean() * 100).round(1)
    for col, pct in coverage.items():
        pct_safe = 0.0 if (pct != pct) else float(pct)  # guard NaN
        bar = "█" * int(pct_safe / 10) + "░" * (10 - int(pct_safe / 10))
        print(f"  {col:<22} {bar}  {pct_safe:5.1f}%")
    print(f"\n  Rows total: {len(df)}")
    if "moneda" in df.columns:
        print(f"\n  Currency split:\n{df['moneda'].value_counts().to_string()}")
    if "precio" in df.columns:
        print(f"\n  Price stats (all):\n{df['precio'].describe().round(0).to_string()}")


# ── CLI ───────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="MercadoLibre car listing scraper for ML AVM dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py                                          # 10-row pilot (50 concurrent)
  python scraper.py --rows 1000                              # 1000-row run
  python scraper.py --rows 50000                             # large overnight run
  python scraper.py --rows 20 --skip-phase1                  # use pre-seeded item_urls.txt
  python scraper.py --rows 1000 --concurrency 10             # limit to 10 parallel browsers
        """,
    )
    p.add_argument(
        "--rows", type=int, default=10,
        help="Number of item rows to scrape (default: 10)",
    )
    p.add_argument(
        "--output", type=str, default=None,
        help="Output CSV path (default: data/car_<rows>rows.csv)",
    )
    p.add_argument(
        "--batch-size", type=int, default=500,
        help="Items per batch before the long anti-bot pause (default: 500)",
    )
    p.add_argument(
        "--concurrency", type=int, default=50,
        help="Parallel browser sessions for Phase 2 (default: 50, max: 50)",
    )
    p.add_argument(
        "--skip-phase1", action="store_true",
        help="Skip listing crawl; read item URLs from data/item_urls.txt",
    )
    p.add_argument(
        "--pages", type=int, default=None,
        help="Number of listing index pages to crawl (auto-calculated if omitted)",
    )
    p.add_argument(
        "--no-coverage", action="store_true",
        help="Skip the coverage report at the end",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    return p.parse_args()


# ── Entry point ───────────────────────────────

def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    rows        = args.rows
    output      = args.output or f"data/car_{rows}rows.csv"
    batch_size  = args.batch_size
    concurrency = max(1, min(args.concurrency, 50))   # clamp to [1, 50]
    # Auto-calculate pages: 48 items/page, fetch 20% extra as URL buffer
    n_pages     = args.pages or max(1, math.ceil(rows * 1.2 / config.ITEMS_PER_PAGE))

    log.info("═══ MercadoLibre car scraper ═══")
    log.info("Target rows  : %d", rows)
    log.info("Output file  : %s", output)
    log.info("Concurrency  : %d", concurrency)
    log.info("Batch size   : %d", batch_size)

    client = _get_client()

    # ── Phase 1 ──────────────────────────────
    urls_file = Path(config.ITEM_URLS_FILE)

    if args.skip_phase1:
        if not urls_file.exists():
            raise SystemExit(
                f"--skip-phase1 specified but {config.ITEM_URLS_FILE} not found. "
                "Create it with one item URL per line."
            )
        item_urls = [u.strip() for u in urls_file.read_text().splitlines() if u.strip()]
        log.info("Phase 1 skipped — loaded %d URLs from %s", len(item_urls), config.ITEM_URLS_FILE)
    else:
        # Load already-collected URLs and resume from the next unseen page
        existing_urls: list[str] = []
        if urls_file.exists():
            existing_urls = [u.strip() for u in urls_file.read_text().splitlines() if u.strip()]

        urls_needed = max(0, n_pages * config.ITEMS_PER_PAGE - len(existing_urls))

        if urls_needed == 0:
            log.info(
                "Phase 1 — already have %d URLs, no new pages needed",
                len(existing_urls),
            )
            item_urls = existing_urls
        else:
            log.info(
                "Phase 1 — have %d URLs; need %d more (cycling through province filters)",
                len(existing_urls), urls_needed,
            )
            new_urls  = collect_item_urls(client, urls_needed, set(existing_urls), concurrency)
            item_urls = existing_urls + new_urls
            urls_file.write_text("\n".join(item_urls))
            log.info(
                "Phase 1 complete — %d new URLs appended; %d total saved to %s",
                len(new_urls), len(item_urls), config.ITEM_URLS_FILE,
            )

        if not item_urls:
            log.error(
                "No item URLs found. The listing pages may be blocked.\n"
                "Workaround: open MercadoLibre in your browser, copy item URLs "
                "into data/item_urls.txt (one per line), then re-run with --skip-phase1."
            )
            return

    target_urls = item_urls[:rows]
    log.info("Using %d URLs (of %d collected)", len(target_urls), len(item_urls))

    # ── Phase 2 ──────────────────────────────
    log.info("Phase 2 — scraping item pages → %s", output)
    n_ok = scrape_items(client, target_urls, output, batch_size, concurrency)

    log.info("═══ Done — %d/%d rows written to %s ═══", n_ok, len(target_urls), output)

    if not args.no_coverage and n_ok > 0:
        print_coverage(output)


if __name__ == "__main__":
    main()
