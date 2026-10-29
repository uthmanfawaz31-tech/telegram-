"""
fiverr.py – Fiverr review scraper + Telegram active-username detector.

Uses Playwright (real headless Chromium) to load the Fiverr gig page,
intercept every XHR call to /gig_page_perseus/reviews, and collect ALL
reviewer usernames across every page — exactly what a real browser does.

No cookies or credentials needed from the user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import models
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FiverrScanRequest(BaseModel):
    fiverr_url: str
    max_reviewers: Optional[int] = 500   # safety cap


class ReviewerResult(BaseModel):
    fiverr_username: str
    display_name: str
    telegram_found: bool
    telegram_username: Optional[str] = None
    telegram_name: Optional[str] = None
    telegram_id: Optional[str] = None


class FiverrScanResponse(BaseModel):
    fiverr_url: str
    seller_username: str
    gig_slug: Optional[str] = None
    total_reviewers_scanned: int
    total_reviews_on_profile: int
    active_on_telegram: int
    not_on_telegram: int
    results: List[ReviewerResult]
    scan_duration_seconds: float
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def _parse_fiverr_url(url: str) -> Tuple[str, Optional[str]]:
    cleaned = re.sub(r'\?.*', '', url.strip().rstrip('/'))
    m = re.search(r'fiverr\.com/([^/?#\s]+)(?:/([^/?#\s]+))?', cleaned)
    if not m:
        raise ValueError(f"Cannot parse a seller username from: {url}")
    seller = m.group(1).lower()
    gig    = m.group(2).lower() if m.group(2) else None
    _SKIP  = {"categories", "pro", "business", "gigs", "inbox", "cp",
              "start_selling", "search", "login", "register", "about"}
    if seller in _SKIP:
        raise ValueError(f"URL does not point to a seller profile: {url}")
    return seller, gig


# ---------------------------------------------------------------------------
# Playwright scraper — intercepts Fiverr's XHR review calls
# ---------------------------------------------------------------------------

async def _scrape_with_playwright(
    gig_url: str,
    seller_url: str,
    max_reviewers: int,
) -> Tuple[List[Dict], int, Optional[str]]:
    """
    Launch a headless Chromium browser, navigate to the Fiverr gig page,
    intercept every /gig_page_perseus/reviews XHR response, keep clicking
    the 'Show more reviews' button until all reviews are loaded.

    Returns (reviewer_list, total_count, error_or_None).
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return [], 0, "playwright not installed — run: pip install playwright && playwright install chromium"

    all_reviewers: Dict[str, Dict] = {}
    total_count   = 0
    error: Optional[str] = None

    def _extract_reviewers_from_response(data: Any) -> Tuple[List[Dict], int]:
        """Parse one XHR response payload into reviewer list + total."""
        reviewers = []
        total = 0
        if isinstance(data, dict):
            # Shape: {"reviews": [...], "pagination": {"total": N}}
            raw = data.get("reviews") or data.get("reviews_list") or []
            pagination = data.get("pagination") or {}
            total = int(pagination.get("total") or data.get("total_count") or 0)
            for rev in raw:
                ro    = rev.get("reviewer") or rev.get("buyer") or rev
                uname = ro.get("username") or rev.get("username") or rev.get("buyerUsername")
                if not uname or not isinstance(uname, str):
                    continue
                uname   = uname.lower().strip()
                display = ro.get("display_name") or ro.get("name") or uname
                reviewers.append({"fiverr_username": uname, "display_name": str(display)})
        return reviewers, total

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
            },
        )
        # Hide webdriver fingerprint
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)
        page = await context.new_page()

        # -------------------------------------------------------------------
        # Intercept all /gig_page_perseus/reviews XHR calls
        # -------------------------------------------------------------------
        xhr_queue: asyncio.Queue = asyncio.Queue()

        async def on_response(response):
            if "gig_page_perseus/reviews" in response.url:
                try:
                    body = await response.json()
                    await xhr_queue.put(body)
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            # ---------------------------------------------------------------
            # Step 1: Navigate to the gig page (stealth headers)
            # ---------------------------------------------------------------
            logger.info(f"Playwright: navigating to {gig_url}")
            await page.goto(gig_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)   # let JS/PerimeterX settle

            # ---------------------------------------------------------------
            # Step 2: Extract page-1 reviewers from the embedded script JSON
            # ---------------------------------------------------------------
            html = await page.content()
            pos  = html.find('"gigId":')
            if pos != -1:
                sc  = html.rfind('<script', 0, pos)
                se  = html.find('</script>', pos)
                raw = html[html.find('>', sc) + 1:se].strip()
                try:
                    gig_data    = json.loads(raw)
                    rev_sec     = gig_data.get("reviews", {})
                    total_count = int(rev_sec.get("total_count", 0))
                    for rev in rev_sec.get("reviews", []):
                        uname = rev.get("username") or rev.get("buyerUsername")
                        if not uname:
                            continue
                        uname = uname.lower().strip()
                        display = rev.get("display_name") or rev.get("name") or uname
                        all_reviewers[uname] = {"fiverr_username": uname, "display_name": str(display)}
                    logger.info(f"Playwright page 1: {len(all_reviewers)} reviewers, total={total_count}")
                except Exception as e:
                    logger.warning(f"Playwright: gig JSON parse error: {e}")

            # ---------------------------------------------------------------
            # Step 3: Drain any XHR responses already captured
            # ---------------------------------------------------------------
            while not xhr_queue.empty():
                body = await xhr_queue.get()
                revs, t = _extract_reviewers_from_response(body)
                if t:
                    total_count = t
                for r in revs:
                    u = r["fiverr_username"]
                    if u not in all_reviewers:
                        all_reviewers[u] = r

            # ---------------------------------------------------------------
            # Step 4: Scroll to reviews, click "See all reviews" to open modal
            # ---------------------------------------------------------------
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6)")
            await page.wait_for_timeout(1500)

            # Click "See all reviews" button to open the reviews modal
            see_all_clicked = False
            for sel in [
                "button:has-text('See all reviews')",
                "button:has-text('see all reviews')",
                "[aria-label*='reviews']",
            ]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.scroll_into_view_if_needed()
                        await btn.click(timeout=5000)
                        see_all_clicked = True
                        logger.info("Playwright: clicked 'See all reviews' — modal should open")
                        await page.wait_for_timeout(4000)  # wait for modal + first XHR
                        break
                except Exception:
                    continue

            if not see_all_clicked:
                logger.warning("Playwright: 'See all reviews' button not found — will try scrolling only")

            # Drain XHR from the modal opening
            while not xhr_queue.empty():
                body = await xhr_queue.get()
                revs, t = _extract_reviewers_from_response(body)
                if t:
                    total_count = t
                for r in revs:
                    u = r["fiverr_username"]
                    if u not in all_reviewers:
                        all_reviewers[u] = r

            # ---------------------------------------------------------------
            # Step 5: Paginate through the reviews modal
            # ---------------------------------------------------------------
            # Selectors for "next page" / "load more" inside the modal
            next_page_selectors = [
                # Numbered pagination — click the next arrow/button
                "[aria-label='Go to next page']",
                "button[aria-label='Next']",
                "button[aria-label='next']",
                ".pagination-arrows button:last-child",
                "button[data-testid='next-page']",
                # Load-more style
                "button:has-text('Load more')",
                "button:has-text('Next')",
                # Modal scroll area selectors (fallback)
                "[role='dialog'] button:has-text('Next')",
            ]

            consecutive_failures = 0
            MAX_PAGES = int(total_count / 10) + 10 if total_count else 90

            for page_num in range(MAX_PAGES):
                if len(all_reviewers) >= max_reviewers:
                    break

                # Scroll the modal/page to ensure buttons visible
                await page.evaluate(
                    "const d = document.querySelector('[role=\"dialog\"]') || document.body;"
                    "d.scrollTop += 800;"
                )
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

                # Try clicking a "next page" or "load more" button
                clicked = False
                for sel in next_page_selectors:
                    try:
                        btn = page.locator(sel).last
                        if await btn.is_visible(timeout=1500):
                            await btn.scroll_into_view_if_needed()
                            await btn.click(timeout=3000)
                            clicked = True
                            logger.info(f"Playwright: page {page_num+2} — clicked '{sel}'")
                            await page.wait_for_timeout(2500)
                            break
                    except Exception:
                        continue

                # Drain XHR queue
                new_this_round = 0
                deadline = asyncio.get_event_loop().time() + 3
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        body = xhr_queue.get_nowait()
                        revs, t = _extract_reviewers_from_response(body)
                        if t:
                            total_count = t
                        for r in revs:
                            u = r["fiverr_username"]
                            if u not in all_reviewers:
                                all_reviewers[u] = r
                                new_this_round += 1
                    except asyncio.QueueEmpty:
                        await asyncio.sleep(0.2)

                logger.info(
                    f"Playwright page {page_num+2}: +{new_this_round} new, "
                    f"total_unique={len(all_reviewers)}/{total_count}"
                )

                if not clicked and new_this_round == 0:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logger.info("Playwright: no more pages — done")
                        break
                else:
                    consecutive_failures = 0

        except Exception as exc:
            logger.error(f"Playwright error: {exc}")
            error = str(exc)
        finally:
            await browser.close()

    # Also scrape seller profile page for any extra reviewers
    try:
        await _add_seller_page_reviewers_async(seller_url, all_reviewers)
    except Exception as e:
        logger.debug(f"Seller page error (non-fatal): {e}")

    return list(all_reviewers.values()), total_count, error


async def _add_seller_page_reviewers_async(
    seller_url: str, existing: Dict[str, Dict]
) -> None:
    """Fetch seller page via httpx and add any extra reviewers."""
    try:
        import httpx
        async with httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.fiverr.com/",
            },
            follow_redirects=True,
            timeout=20,
        ) as client:
            resp = await client.get(seller_url)
            html = resp.text
            for m in re.finditer(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE):
                c = m.group(1).strip()
                if not (c.startswith('{') and 'reviewsData' in c):
                    continue
                try:
                    data    = json.loads(c)
                    rd      = data.get("reviewsData", {})
                    selling = rd.get("selling_reviews", {}) if isinstance(rd, dict) else {}
                    raw     = selling.get("reviews", []) if isinstance(selling, dict) else []
                    for rev in raw:
                        uname = rev.get("username") or rev.get("buyerUsername")
                        if not uname:
                            continue
                        uname = uname.lower().strip()
                        if uname not in existing:
                            display = rev.get("display_name") or rev.get("name") or uname
                            existing[uname] = {"fiverr_username": uname, "display_name": str(display)}
                except Exception:
                    pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

_TG_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$')


def _valid_tg_username(u: str) -> bool:
    return bool(_TG_RE.match(u))


async def _check_telegram(service: TelegramService, username: str) -> Dict[str, Any]:
    try:
        entity   = await service.client.get_entity(f"@{username}")
        tg_uname = getattr(entity, "username", None)
        first    = getattr(entity, "first_name", "") or ""
        last     = getattr(entity, "last_name",  "") or ""
        tg_name  = f"{first} {last}".strip() or tg_uname or str(entity.id)
        return {"found": True, "telegram_username": tg_uname,
                "telegram_name": tg_name, "telegram_id": str(entity.id)}
    except Exception:
        return {"found": False}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=FiverrScanResponse)
async def scan_fiverr_profile(
    payload: FiverrScanRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Launch a headless Chrome browser to scrape ALL reviewer usernames from
    a Fiverr gig page, then check each against Telegram.
    """
    start = time.monotonic()

    account = (
        db.query(models.TelegramAccount)
        .filter(models.TelegramAccount.is_connected == True)
        .first()
    )
    if not account or not account.session_string:
        raise HTTPException(status_code=401,
                            detail="SESSION_MISSING: Connect a Telegram account first.")

    try:
        seller_slug, gig_slug = _parse_fiverr_url(payload.fiverr_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    gig_url    = (f"https://www.fiverr.com/{seller_slug}/{gig_slug}"
                  if gig_slug else f"https://www.fiverr.com/{seller_slug}")
    seller_url = f"https://www.fiverr.com/{seller_slug}"
    max_rev    = max(10, min(payload.max_reviewers or 500, 1000))

    # Scrape Fiverr using Playwright
    reviewer_list, total_count, scrape_error = await _scrape_with_playwright(
        gig_url, seller_url, max_rev
    )

    logger.info(
        f"Scrape done: {len(reviewer_list)} unique reviewers "
        f"(profile total={total_count}), seller={seller_slug}"
    )

    # ------------------------------------------------------------------
    # Telegram checks
    # ------------------------------------------------------------------
    service = TelegramService(
        session_string=account.session_string,
        api_id=account.api_id,
        api_hash=account.api_hash,
    )

    results: List[ReviewerResult] = []
    active_count = 0

    try:
        await service.connect()
        for reviewer in reviewer_list:
            uname   = reviewer["fiverr_username"]
            display = reviewer.get("display_name", uname)
            tg      = (await _check_telegram(service, uname)
                       if _valid_tg_username(uname) else {"found": False})

            result = ReviewerResult(
                fiverr_username=uname,
                display_name=display,
                telegram_found=tg["found"],
                telegram_username=tg.get("telegram_username"),
                telegram_name=tg.get("telegram_name"),
                telegram_id=tg.get("telegram_id"),
            )
            results.append(result)
            if tg["found"]:
                active_count += 1
            await asyncio.sleep(0.4)

    except Exception as exc:
        logger.error(f"Telegram error: {exc}")
        scrape_error = (scrape_error or "") + f" | Telegram: {exc}"
    finally:
        await service.disconnect()

    return FiverrScanResponse(
        fiverr_url=payload.fiverr_url,
        seller_username=seller_slug,
        gig_slug=gig_slug,
        total_reviewers_scanned=len(results),
        total_reviews_on_profile=total_count,
        active_on_telegram=active_count,
        not_on_telegram=len(results) - active_count,
        results=results,
        scan_duration_seconds=round(time.monotonic() - start, 2),
        error=scrape_error,
    )
