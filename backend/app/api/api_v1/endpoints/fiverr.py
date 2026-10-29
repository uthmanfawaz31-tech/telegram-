"""
fiverr.py – Fiverr review scraper + Telegram active-username detector.

Uses curl_cffi with Chrome TLS impersonation to bypass PerimeterX/Cloudflare.
No session cookies required from the user — the Chrome fingerprint is enough.

Strategy:
  1. Fetch gig page using curl_cffi (Chrome110 impersonation) → embedded JSON
     gives first 10 reviews + total_count + gig_id
  2. Call /gig_page_perseus/reviews?gig_id=...&page=N for every page until done
  3. Also fetch seller profile page for additional reviewer data
  4. Check every unique username against Telegram via get_entity
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import models
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)
router = APIRouter()

# Thread pool for running sync curl_cffi calls inside async FastAPI
_executor = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FiverrScanRequest(BaseModel):
    fiverr_url: str
    max_pages: Optional[int] = 80   # up to 80 pages × 10 reviews = 800 reviewers


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
# Fiverr scraping (sync — run in thread pool)
# ---------------------------------------------------------------------------

def _scrape_all_reviews(gig_url: str, seller_url: str, max_pages: int) -> Tuple[List[Dict], int, Optional[str]]:
    """
    Scrape all reviewer usernames from a Fiverr gig/seller page.
    Uses curl_cffi Chrome110 impersonation to bypass PerimeterX.
    Returns (reviewer_list, total_count, error_message_or_None).
    """
    try:
        from curl_cffi.requests import Session
    except ImportError:
        return [], 0, "curl_cffi not installed. Run: pip install curl_cffi"

    all_reviewers: Dict[str, Dict] = {}
    total_count = 0
    error: Optional[str] = None

    with Session(impersonate="chrome110") as s:
        headers = {
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.fiverr.com/",
        }

        # ---------------------------------------------------------------
        # Page 1: embedded JSON in gig page
        # ---------------------------------------------------------------
        try:
            resp = s.get(gig_url, headers=headers, timeout=30)
            html = resp.text

            # Extract CSRF token
            csrf_m = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', html)
            csrf   = csrf_m.group(1) if csrf_m else ""

            # Collect response cookies for subsequent XHR calls
            session_cookies = dict(resp.cookies)

            # Parse embedded gig JSON
            gig_id, p1_reviewers, total_count, has_next = _parse_gig_page(html)
            for r in p1_reviewers:
                all_reviewers[r["fiverr_username"]] = r

            logger.info(
                f"Gig page 1: {len(p1_reviewers)} reviewers, "
                f"total={total_count}, gig_id={gig_id}, has_next={has_next}"
            )

            # -----------------------------------------------------------
            # Pages 2 … max_pages via XHR
            # -----------------------------------------------------------
            if gig_id and has_next:
                xhr_headers = {
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "en-US,en;q=0.9",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRF-Token": csrf,
                    "Referer": gig_url,
                }

                for page in range(2, max_pages + 1):
                    if not has_next:
                        break
                    time.sleep(0.6)

                    params = f"gig_id={gig_id}&page={page}&filter=all&order_type=relevant"
                    api_url = f"https://www.fiverr.com/gig_page_perseus/reviews?{params}"

                    r = s.get(api_url, headers=xhr_headers, cookies=session_cookies, timeout=20)

                    ct      = r.headers.get("content-type", "")
                    is_json = r.text.strip().startswith(("{", "["))

                    if r.status_code != 200 or not is_json:
                        logger.warning(f"XHR page {page}: status={r.status_code}, not JSON — stopping")
                        break

                    data     = r.json()
                    raw_revs = data.get("reviews") or data.get("reviews_list") or []

                    page_reviewers = []
                    for rev in raw_revs:
                        ro    = rev.get("reviewer") or rev.get("buyer") or rev
                        uname = ro.get("username") or rev.get("username") or rev.get("buyerUsername")
                        if not uname or not isinstance(uname, str):
                            continue
                        uname   = uname.lower().strip()
                        display = ro.get("display_name") or ro.get("name") or uname
                        page_reviewers.append({"fiverr_username": uname, "display_name": str(display)})

                    pagination = data.get("pagination") or {}
                    p_total    = int(pagination.get("total") or data.get("total_count") or total_count)
                    per_page   = int(pagination.get("per_page") or 10)
                    has_next   = page < math.ceil(p_total / per_page) if p_total else bool(len(raw_revs) >= 8)

                    added_new = False
                    for r2 in page_reviewers:
                        u = r2["fiverr_username"]
                        if u not in all_reviewers:
                            all_reviewers[u] = r2
                            added_new = True

                    logger.info(
                        f"XHR page {page}: {len(page_reviewers)} reviewers, "
                        f"unique={len(all_reviewers)}, has_next={has_next}"
                    )

                    if not added_new:
                        break

        except Exception as exc:
            logger.error(f"Gig page scrape error: {exc}")
            error = str(exc)

        # ---------------------------------------------------------------
        # Seller profile page: extra featured reviewers
        # ---------------------------------------------------------------
        try:
            time.sleep(0.8)
            resp2 = s.get(seller_url, headers=headers, timeout=30)
            added = _add_seller_page_reviewers(resp2.text, all_reviewers)
            logger.info(f"Seller page added {added} extra reviewers")
        except Exception as exc:
            logger.debug(f"Seller page error (non-fatal): {exc}")

    return list(all_reviewers.values()), total_count, error


def _parse_gig_page(html: str) -> Tuple[Optional[int], List[Dict], int, bool]:
    """Parse embedded gig JSON. Returns (gig_id, reviewers, total_count, has_next)."""
    pos = html.find('"gigId":')
    if pos == -1:
        pos = html.find('"gig_id":')
    if pos == -1:
        return None, [], 0, False

    sc = html.rfind('<script', 0, pos)
    se = html.find('</script>', pos)
    if sc == -1 or se == -1:
        return None, [], 0, False

    raw = html[html.find('>', sc) + 1:se].strip()
    try:
        data = json.loads(raw)
    except Exception:
        return None, [], 0, False

    gig_id      = data.get("general", {}).get("gigId")
    rev_section = data.get("reviews", {})
    total       = int(rev_section.get("total_count", 0))
    has_next    = bool(rev_section.get("has_next", False))
    raw_reviews = rev_section.get("reviews", [])

    reviewers = []
    seen: set = set()
    for rev in raw_reviews:
        uname = rev.get("username") or rev.get("buyerUsername") or rev.get("buyer_username")
        if not uname or not isinstance(uname, str):
            continue
        uname = uname.lower().strip()
        if uname in seen:
            continue
        seen.add(uname)
        display = rev.get("display_name") or rev.get("name") or uname
        reviewers.append({"fiverr_username": uname, "display_name": str(display)})

    return gig_id, reviewers, total, has_next


def _add_seller_page_reviewers(html: str, existing: Dict[str, Dict]) -> int:
    """Add reviewers from seller profile page's reviewsData JSON. Returns count added."""
    added = 0
    for m in re.finditer(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE):
        c = m.group(1).strip()
        if not (c.startswith('{') and 'reviewsData' in c):
            continue
        try:
            data = json.loads(c)
        except Exception:
            continue
        rd      = data.get("reviewsData", {})
        selling = rd.get("selling_reviews", {}) if isinstance(rd, dict) else {}
        raw     = selling.get("reviews", []) if isinstance(selling, dict) else []
        for rev in raw:
            uname = rev.get("username") or rev.get("buyerUsername")
            if not uname or not isinstance(uname, str):
                continue
            uname = uname.lower().strip()
            if uname not in existing:
                display = rev.get("display_name") or rev.get("name") or uname
                existing[uname] = {"fiverr_username": uname, "display_name": str(display)}
                added += 1
    return added


# ---------------------------------------------------------------------------
# Telegram username validation + lookup
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
    Scrape ALL reviewer usernames from a Fiverr gig/seller page using Chrome
    TLS impersonation (curl_cffi), then check each against Telegram.
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
    max_pages  = max(1, min(payload.max_pages or 80, 80))

    # Run the sync curl_cffi scraper in a thread pool
    loop = asyncio.get_event_loop()
    reviewer_list, total_count, scrape_error = await loop.run_in_executor(
        _executor, _scrape_all_reviews, gig_url, seller_url, max_pages
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
            tg      = await _check_telegram(service, uname) if _valid_tg_username(uname) else {"found": False}

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
