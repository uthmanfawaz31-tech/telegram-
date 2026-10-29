"""
fiverr.py – Fiverr review scraper + Telegram active-username detector.

Scraping strategy (confirmed working by live tests):

  SOURCE A – Gig page (https://fiverr.com/<seller>/<gig>)
    Fiverr bakes a large JSON blob into every gig page's <script> tag.
    data["reviews"]["reviews"]  → up to 5 reviewer objects (first batch only)
    data["reviews"]["total_count"] → total reviews on this gig
    data["general"]["gigId"]    → gig ID integer

  SOURCE B – Seller profile page (https://fiverr.com/<seller>)
    A separate JSON blob (Script 6) contains:
    data["reviewsData"]["selling_reviews"]["reviews"] → up to 4 featured reviewer objects
    These are DIFFERENT reviewers from Source A.

  Combined, both sources yield ~9 unique reviewer usernames per seller.
  Fiverr hard-blocks all pagination APIs without a real browser session
  (PerimeterX fingerprint cookies required). This is a platform restriction,
  not a bug in this code.

  After collecting usernames, each is validated against Telegram's username
  rules and checked via get_entity to detect active accounts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
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
    fiverr_cookies: Optional[str] = None   # raw cookie header string from logged-in browser session
    max_pages: Optional[int] = 30          # max pages of reviews to fetch (1 page = ~10 reviews)


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
    total_reviews_on_profile: int          # full count Fiverr reports
    active_on_telegram: int
    not_on_telegram: int
    results: List[ReviewerResult]
    scan_duration_seconds: float
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------

_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Referer": "https://www.fiverr.com/",
    "DNT": "1",
}


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def _parse_fiverr_url(url: str) -> Tuple[str, Optional[str]]:
    """
    Returns (seller_slug, gig_slug_or_None).
    Handles:
      https://www.fiverr.com/username
      https://www.fiverr.com/username/gig-slug?...
    """
    cleaned = re.sub(r'\?.*', '', url.strip().rstrip('/'))
    m = re.search(r'fiverr\.com/([^/?#\s]+)(?:/([^/?#\s]+))?', cleaned)
    if not m:
        raise ValueError(f"Cannot parse a seller username from: {url}")
    seller = m.group(1).lower()
    gig    = m.group(2).lower() if m.group(2) else None
    _SKIP = {"categories", "pro", "business", "gigs", "inbox", "cp",
             "start_selling", "search", "login", "register", "about"}
    if seller in _SKIP:
        raise ValueError(f"URL does not point to a seller profile: {url}")
    return seller, gig


# ---------------------------------------------------------------------------
# Page parsing helpers
# ---------------------------------------------------------------------------

def _all_json_scripts(html: str) -> List[dict]:
    """Return all <script> blocks that parse as JSON objects."""
    results = []
    for m in re.finditer(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE):
        content = m.group(1).strip()
        if content.startswith('{') and len(content) > 100:
            try:
                results.append(json.loads(content))
            except Exception:
                pass
    return results


def _extract_gig_page_reviewers(html: str) -> Tuple[List[Dict], int, Optional[int]]:
    """
    SOURCE A: Parse the gig page embedded JSON.
    Returns (reviewer_list, total_count_on_gig, gig_id).
    reviewer_list entries: {"fiverr_username": str, "display_name": str}
    """
    # Find the <script> that contains "gigId"
    for pattern in ['"gigId":', '"gig_id":']:
        pos = html.find(pattern)
        if pos != -1:
            break
    else:
        return [], 0, None

    script_open  = html.rfind('<script', 0, pos)
    script_close = html.find('</script>', pos)
    if script_open == -1 or script_close == -1:
        return [], 0, None

    inner_start = html.find('>', script_open) + 1
    raw = html[inner_start:script_close].strip()

    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"Gig page JSON parse error: {e}")
        return [], 0, None

    gig_id      = data.get("general", {}).get("gigId")
    rev_section = data.get("reviews", {})
    total_count = int(rev_section.get("total_count", 0))
    raw_reviews = rev_section.get("reviews", [])

    reviewers = []
    seen: set = set()
    for rev in raw_reviews:
        uname = (
            rev.get("username") or
            rev.get("buyerUsername") or
            rev.get("buyer_username")
        )
        if not uname or not isinstance(uname, str):
            continue
        uname = uname.lower().strip()
        if uname in seen:
            continue
        seen.add(uname)
        display = rev.get("display_name") or rev.get("name") or uname
        reviewers.append({"fiverr_username": uname, "display_name": str(display)})

    logger.info(f"Gig page: {len(reviewers)} unique reviewers, total_count={total_count}, gig_id={gig_id}")
    return reviewers, total_count, gig_id


def _extract_seller_page_reviewers(html: str) -> List[Dict]:
    """
    SOURCE B: Parse the seller profile page's reviewsData JSON.
    Returns reviewer_list with the featured selling_reviews.
    """
    for script_data in _all_json_scripts(html):
        reviews_data = script_data.get("reviewsData")
        if not reviews_data or not isinstance(reviews_data, dict):
            continue

        selling = reviews_data.get("selling_reviews", {})
        if not isinstance(selling, dict):
            continue

        raw_reviews = selling.get("reviews", [])
        reviewers = []
        seen: set = set()
        for rev in raw_reviews:
            uname = (
                rev.get("username") or
                rev.get("buyerUsername") or
                rev.get("buyer_username")
            )
            if not uname or not isinstance(uname, str):
                continue
            uname = uname.lower().strip()
            if uname in seen:
                continue
            seen.add(uname)
            display = rev.get("display_name") or rev.get("name") or uname
            reviewers.append({"fiverr_username": uname, "display_name": str(display)})

        logger.info(f"Seller page: {len(reviewers)} unique reviewers from selling_reviews")
        return reviewers

    return []


# ---------------------------------------------------------------------------
# Reviewers XHR API  (pages 2, 3, … — requires session cookies)
# ---------------------------------------------------------------------------

async def _fetch_xhr_page(
    client,
    gig_id: int,
    page: int,
    csrf_token: str,
    cookie_header: str,
    referer: str,
) -> Tuple[List[Dict], bool]:
    """
    Call Fiverr's internal reviews XHR endpoint for pages 2+.
    Requires valid session cookies from a logged-in browser.
    Returns (reviewer_list, has_more).
    """
    headers = {
        "User-Agent": _BROWSER["User-Agent"],
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
        "X-CSRF-Token": csrf_token,
        "Cookie": cookie_header,
    }
    params = f"gig_id={gig_id}&page={page}&filter=all&order_type=relevant"
    url = f"https://www.fiverr.com/gig_page_perseus/reviews?{params}"

    try:
        resp = await client.get(url, headers=headers, timeout=20)
        ct = resp.headers.get("content-type", "")
        # If we get HTML back, the session cookies didn't work
        if resp.status_code != 200 or "text/html" in ct:
            logger.debug(f"XHR page {page}: blocked (status={resp.status_code}, ct={ct})")
            return [], False

        body = resp.text.strip()
        if not (body.startswith('{') or body.startswith('[')):
            return [], False

        data = resp.json()
        # Response shape: {"reviews": [...], "pagination": {"total": N, "page": P, "per_page": M}}
        raw = (
            data.get("reviews") or
            data.get("reviews_list") or
            data.get("items") or
            []
        )
        reviewers = []
        for rev in raw:
            reviewer_obj = rev.get("reviewer") or rev.get("buyer") or rev
            uname = (
                reviewer_obj.get("username") or
                rev.get("username") or
                rev.get("buyerUsername")
            )
            if not uname or not isinstance(uname, str):
                continue
            uname = uname.lower().strip()
            display = reviewer_obj.get("display_name") or reviewer_obj.get("name") or uname
            reviewers.append({"fiverr_username": uname, "display_name": str(display)})

        pagination = data.get("pagination") or {}
        total      = int(pagination.get("total") or data.get("total_count") or 0)
        per_page   = int(pagination.get("per_page") or 10)
        has_more   = (page < math.ceil(total / per_page)) if total else bool(len(raw) >= 8)
        logger.info(f"XHR page {page}: got {len(reviewers)} reviewers, total={total}, has_more={has_more}")
        return reviewers, has_more

    except Exception as e:
        logger.debug(f"XHR page {page} exception: {e}")
        return [], False


def _parse_cookie_string(cookie_str: str) -> str:
    """Clean and normalise a pasted cookie header string."""
    return cookie_str.strip()


# ---------------------------------------------------------------------------
# Telegram username validation
# ---------------------------------------------------------------------------

# Telegram username rules: 5–32 chars, letters/digits/underscore, starts with letter
_TG_USERNAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$')


def _valid_tg_username(username: str) -> bool:
    return bool(_TG_USERNAME_RE.match(username))


async def _check_telegram(service: TelegramService, username: str) -> Dict[str, Any]:
    try:
        entity = await service.client.get_entity(f"@{username}")
        tg_uname = getattr(entity, "username", None)
        first    = getattr(entity, "first_name", "") or ""
        last     = getattr(entity, "last_name",  "") or ""
        tg_name  = f"{first} {last}".strip() or tg_uname or str(entity.id)
        return {
            "found": True,
            "telegram_username": tg_uname,
            "telegram_name":     tg_name,
            "telegram_id":       str(entity.id),
        }
    except Exception:
        return {"found": False}


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=FiverrScanResponse)
async def scan_fiverr_profile(
    payload: FiverrScanRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    1. Scrape reviewer usernames from a Fiverr gig/seller page.
       - Without cookies: scrapes ~9 publicly embedded reviews.
       - With fiverr_cookies: uses the session to paginate through ALL reviews.
    2. Check each reviewer username against Telegram.
    3. Return full results with active/inactive split.
    """
    start = time.monotonic()

    # Require a connected Telegram account
    account = (
        db.query(models.TelegramAccount)
        .filter(models.TelegramAccount.is_connected == True)
        .first()
    )
    if not account or not account.session_string:
        raise HTTPException(
            status_code=401,
            detail="SESSION_MISSING: Connect a Telegram account first.",
        )

    # Parse URL
    try:
        seller_slug, gig_slug = _parse_fiverr_url(payload.fiverr_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        import httpx
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="httpx is required. Add it to requirements.txt and restart.",
        )

    gig_url    = (
        f"https://www.fiverr.com/{seller_slug}/{gig_slug}"
        if gig_slug else
        f"https://www.fiverr.com/{seller_slug}"
    )
    seller_url = f"https://www.fiverr.com/{seller_slug}"

    # Build request headers (include cookies if provided)
    session_cookie = _parse_cookie_string(payload.fiverr_cookies) if payload.fiverr_cookies else ""
    base_headers = dict(_BROWSER)
    if session_cookie:
        base_headers["Cookie"] = session_cookie

    all_reviewers: Dict[str, Dict] = {}  # username → reviewer dict (deduped)
    total_count_on_profile = 0
    scrape_error: Optional[str] = None

    async with httpx.AsyncClient(
        headers=base_headers,
        follow_redirects=True,
        timeout=30,
    ) as client:

        # ------------------------------------------------------------------
        # SOURCE A: Gig page → first batch of reviewers + gig_id + total_count
        # ------------------------------------------------------------------
        gig_id: Optional[int] = None
        csrf_token = ""
        has_next = False
        try:
            resp = await client.get(gig_url)
            resp.raise_for_status()

            # Extract CSRF token for XHR requests
            csrf_m = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', resp.text)
            csrf_token = csrf_m.group(1) if csrf_m else ""

            # Merge response cookies back into our cookie string
            if resp.cookies:
                resp_cookie_parts = [f"{k}={v}" for k, v in resp.cookies.items()]
                if session_cookie:
                    session_cookie = session_cookie + "; " + "; ".join(resp_cookie_parts)
                else:
                    session_cookie = "; ".join(resp_cookie_parts)

            page_a_reviewers, total_count_on_profile, gig_id = _extract_gig_page_reviewers(resp.text)
            # Determine if there are more pages
            for script_d in _all_json_scripts(resp.text):
                rev_sec = script_d.get("reviews", {})
                if rev_sec and rev_sec.get("has_next") is not None:
                    has_next = bool(rev_sec.get("has_next", False))
                    break

            for r in page_a_reviewers:
                all_reviewers[r["fiverr_username"]] = r

            logger.info(
                f"Gig page 1: {len(page_a_reviewers)} reviewers, "
                f"total={total_count_on_profile}, gig_id={gig_id}, has_next={has_next}"
            )
        except Exception as exc:
            logger.error(f"Source A (gig page) error: {exc}")
            scrape_error = f"Gig page error: {exc}"

        # ------------------------------------------------------------------
        # SOURCE B: Seller profile page → additional featured reviewers
        # ------------------------------------------------------------------
        await asyncio.sleep(0.8)
        try:
            resp2 = await client.get(seller_url)
            resp2.raise_for_status()
            page_b_reviewers = _extract_seller_page_reviewers(resp2.text)
            added_from_b = 0
            for r in page_b_reviewers:
                uname = r["fiverr_username"]
                if uname not in all_reviewers:
                    all_reviewers[uname] = r
                    added_from_b += 1
            logger.info(f"Source B (seller page) added {added_from_b} new unique reviewers")
        except Exception as exc:
            logger.error(f"Source B (seller page) error: {exc}")

        # ------------------------------------------------------------------
        # SOURCE C: XHR pagination (only works with valid session cookies)
        # ------------------------------------------------------------------
        if gig_id and session_cookie and has_next:
            max_pages = max(1, min(payload.max_pages or 30, 80))
            logger.info(f"Starting XHR pagination with session cookies (max_pages={max_pages})")

            for page in range(2, max_pages + 1):
                if not has_next:
                    break

                await asyncio.sleep(0.7)  # polite delay
                page_revs, has_next = await _fetch_xhr_page(
                    client, gig_id, page, csrf_token, session_cookie, gig_url
                )

                if not page_revs:
                    logger.info(f"XHR page {page}: no results — stopping pagination")
                    if page == 2:
                        # First XHR page failed — session cookies likely invalid/expired
                        scrape_error = (
                            (scrape_error or "") +
                            " | Session cookies did not unlock pagination. "
                            "Please copy fresh cookies from your browser."
                        )
                    break

                added_new = False
                for r in page_revs:
                    uname = r["fiverr_username"]
                    if uname not in all_reviewers:
                        all_reviewers[uname] = r
                        added_new = True

                logger.info(
                    f"XHR page {page}: {len(page_revs)} reviewers, "
                    f"total_unique={len(all_reviewers)}, has_next={has_next}"
                )

                if not added_new:
                    break  # No new usernames — reached the end
        elif gig_id and not session_cookie:
            logger.info("No session cookies provided — skipping XHR pagination")

    reviewer_list = list(all_reviewers.values())
    logger.info(
        f"Fiverr scrape done: {len(reviewer_list)} unique reviewers "
        f"(out of {total_count_on_profile} total on profile). "
        f"seller={seller_slug}"
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

            # Skip usernames that cannot possibly be Telegram usernames
            if _valid_tg_username(uname):
                tg = await _check_telegram(service, uname)
            else:
                tg = {"found": False}

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

            await asyncio.sleep(0.4)   # stay under Telegram rate-limit

    except Exception as exc:
        logger.error(f"Telegram check error: {exc}")
        scrape_error = (scrape_error or "") + f" | Telegram: {exc}"
    finally:
        await service.disconnect()

    return FiverrScanResponse(
        fiverr_url=payload.fiverr_url,
        seller_username=seller_slug,
        gig_slug=gig_slug,
        total_reviewers_scanned=len(results),
        total_reviews_on_profile=total_count_on_profile,
        active_on_telegram=active_count,
        not_on_telegram=len(results) - active_count,
        results=results,
        scan_duration_seconds=round(time.monotonic() - start, 2),
        error=scrape_error,
    )
