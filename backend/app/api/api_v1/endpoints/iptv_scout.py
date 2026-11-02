"""
iptv_scout.py – Telegram Group Scout for IPTV Leads & Inquiries with Auto-Translation.

Scans any Telegram group (by invite link or public username),
retrieves message history, extracts usernames, dates, timestamps,
message content, detects non-English languages, translates them
automatically to English, and categorizes prospective IPTV buyers/leads.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from telethon import errors
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import (
    Channel,
    Chat,
    ChatInvite,
    ChatInviteAlready,
    User,
)

from app.core.db import get_db
from app.models import models
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Language Mapping
# ---------------------------------------------------------------------------

LANG_MAP = {
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ar": "Arabic",
    "ru": "Russian",
    "tr": "Turkish",
    "nl": "Dutch",
    "pl": "Polish",
    "el": "Greek",
    "sv": "Swedish",
    "ro": "Romanian",
    "hi": "Hindi",
    "fa": "Persian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "uk": "Ukrainian",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "cs": "Czech",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "he": "Hebrew",
}

# ---------------------------------------------------------------------------
# Multilingual IPTV Keyword & Intent Patterns
# ---------------------------------------------------------------------------

IPTV_RULES = [
    # High Intent: Buying / Requesting Provider / Subscriptions (English + Multilingual)
    (
        re.compile(
            # English
            r"\b(need|want|looking\s+for|search(?:ing)?\s+for|recommend(?:ation)?|best|good|reliable|cheap|any|who\s+sells?|selling)\b.*?\b(iptv|m3u|provider|subscription|sub)\b|"
            r"\b(iptv|sub|subscription)\b.*?\b(provider|recommendation|dm\s+me|pm\s+me|cost|price|buy|seller|reliable|good)\b|"
            r"\b(anyone\s+(?:got|have|sell)\s+(?:a\s+)?(?:good\s+)?iptv)\b|"
            r"\b(i\s+need\s+iptv)\b|"
            # Spanish: busco iptv, necesito iptv, quien vende iptv
            r"\b(busco|necesito|quiero|recomiendan?|quien\s+vende|alguien\s+tiene)\b.*?\b(iptv|m3u|servidor|servicio|proveedor|cuenta)\b|"
            # French: cherche iptv, besoin iptv, abonnement iptv
            r"\b(cherche|besoin|recherche|qui\s+vend|quelqu['\s]un\s+a)\b.*?\b(iptv|m3u|abonnement|fournisseur|serveur)\b|"
            # Italian: cerco iptv, serve iptv, abbonamento iptv
            r"\b(cerco|serve|chi\s+vende|qualcuno\s+ha)\b.*?\b(iptv|m3u|abbonamento|fornitore|server)\b|"
            # German: suche iptv, brauche iptv, wer hat iptv
            r"\b(suche|brauche|wer\s+hat|wer\s+verkauft)\b.*?\b(iptv|m3u|anbieter|abo|linie)\b|"
            # Portuguese: procuro iptv, preciso iptv, quem vende
            r"\b(procuro|preciso|quero|quem\s+vende|alguem\s+tem)\b.*?\b(iptv|m3u|servidor|lista|plano)\b|"
            # Arabic
            r"(ابحث\s+عن|اريد|محتاج|مين\s+عنده|بدي|افضل|عايز)\s+.*?(iptv|اشتراك|سيرفر|قنوات)",
            re.IGNORECASE,
        ),
        "High",
        "Seeking IPTV Provider / Subscription",
    ),
    # High Intent: Requesting Trials (Multilingual)
    (
        re.compile(
            # English
            r"\b(free\s+trial|iptv\s+trial|test\s+line|trial\s+line|test\s+link|trial\s+link|test\s+account|24h\s+trial|need\s+a\s+trial|trial\s+please|free\s+test|trial\s+code|give\s+me\s+trial)\b|"
            # Spanish: prueba gratis, demo iptv, test 24h
            r"\b(prueba\s+gratis|demo\s+iptv|prueba\s+de\s+iptv|test\s+24h|cuenta\s+demo)\b|"
            # French: test gratuit, essai gratuit, test 24h
            r"\b(test\s+gratuit|essai\s+gratuit|test\s+24h|essai\s+iptv)\b|"
            # Italian: prova gratis, test gratuito
            r"\b(prova\s+gratis|test\s+gratuito|prova\s+iptv)\b|"
            # German: test linie, probeabo, kostenlos testen
            r"\b(testlinie|kostenlos\s+testen|probe\s+iptv)\b|"
            # Portuguese: teste gratis, teste de 24h
            r"\b(teste\s+gratis|teste\s+gratuito|teste\s+iptv)\b|"
            # Arabic
            r"(تجربة|تست|تجريبي|طلب\s+تجربة)\s+.*?(iptv|اشتراك|سيرفر)",
            re.IGNORECASE,
        ),
        "High",
        "Requesting Free Trial / Test",
    ),
    # Medium Intent: Devices, Players & Setups
    (
        re.compile(
            r"\b(tivimate|ti-vi-mate|smarters|iptv\s*smarters|xciptv|xcip\s*tv|ibo\s*player|firestick|fire\s*stick|fire\s*tv|mag\s*box|stbemu|smartone|netiptv|ssiptv|formuler)\b",
            re.IGNORECASE,
        ),
        "Medium",
        "App / Device Setup (TiviMate/Firestick/etc.)",
    ),
    # Medium Intent: Playlist, Channels, Tech Specs
    (
        re.compile(
            r"\b(m3u|m3u8|xtream\s*codes?|epg|catchup|catch-up|vod|sports\s*channels?|sky\s*sports?|tnt\s*sports?|premier\s*league|epl|ppv|anti[\s-]?freeze|buffer(?:ing)?)\b",
            re.IGNORECASE,
        ),
        "Medium",
        "Channels / Formats / Tech Specs",
    ),
    # General Mention
    (
        re.compile(r"\b(iptv|ott)\b", re.IGNORECASE),
        "General",
        "General IPTV Discussion",
    ),
]


def _analyze_iptv_intent(text: str) -> Tuple[bool, str, Optional[str], List[str]]:
    """
    Evaluates message text for IPTV relevance and detects intent category.
    Returns: (is_related, relevance_score, intent_category, matched_keywords)
    """
    matched_keywords: List[str] = []
    top_score = "None"
    top_category = None

    score_rank = {"High": 3, "Medium": 2, "General": 1, "None": 0}

    for pattern, score, category in IPTV_RULES:
        matches = pattern.findall(text)
        if matches:
            for m in matches:
                if isinstance(m, tuple):
                    for sub in m:
                        if sub and sub.strip():
                            clean_m = sub.strip()
                            if clean_m.lower() not in [k.lower() for k in matched_keywords]:
                                matched_keywords.append(clean_m)
                elif isinstance(m, str) and m.strip():
                    clean_m = m.strip()
                    if clean_m.lower() not in [k.lower() for k in matched_keywords]:
                        matched_keywords.append(clean_m)

            if score_rank[score] > score_rank[top_score]:
                top_score = score
                top_category = category

    is_related = top_score != "None"
    return is_related, top_score, top_category, matched_keywords


async def _translate_to_english(
    text: str, client: httpx.AsyncClient
) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Detects language and translates to English if non-English.
    Returns: (translated_english_text, detected_language_name, is_translated)
    """
    if not text or not text.strip():
        return None, None, False

    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "en",
            "dt": "t",
            "q": text[:1500],
        }
        res = await client.get(url, params=params, timeout=4.0)
        if res.status_code == 200:
            data = res.json()
            detected_code = (
                data[2]
                if len(data) > 2 and isinstance(data[2], str)
                else "auto"
            )
            detected_code_clean = detected_code.lower().split("-")[0]

            translated_parts = []
            if data and isinstance(data[0], list):
                for part in data[0]:
                    if part and isinstance(part, list) and len(part) > 0 and part[0]:
                        translated_parts.append(part[0])
            translated_text = "".join(translated_parts).strip()

            if (
                detected_code_clean != "en"
                and translated_text
                and translated_text.lower() != text.strip().lower()
            ):
                lang_name = LANG_MAP.get(detected_code_clean, detected_code.upper())
                return translated_text, lang_name, True
            elif detected_code_clean == "en":
                return None, "English", False
    except Exception as e:
        logger.debug(f"Translation note: {e}")

    return None, None, False


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IPTVScoutRequest(BaseModel):
    group_link: str
    limit: Optional[int] = Field(200, ge=10, le=1000)
    filter_iptv_only: Optional[bool] = True
    custom_keywords: Optional[str] = None
    auto_translate: Optional[bool] = True


class MessageLead(BaseModel):
    message_id: int
    sender_id: Optional[str] = None
    username: Optional[str] = None
    display_name: str
    is_bot: bool = False
    date_str: str
    date_iso: str
    message_text: str
    translated_text: Optional[str] = None
    detected_language: Optional[str] = None
    is_translated: bool = False
    is_iptv_related: bool
    relevance_score: str  # "High", "Medium", "General", "None"
    intent_category: Optional[str] = None
    matched_keywords: List[str] = []


class IPTVScoutResponse(BaseModel):
    group_link: str
    group_title: str
    group_id: str
    group_username: Optional[str] = None
    total_scanned: int
    total_leads: int
    high_intent_count: int
    unique_users_count: int
    scan_duration_seconds: float
    leads: List[MessageLead]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/scan", response_model=IPTVScoutResponse)
async def scan_telegram_group(
    payload: IPTVScoutRequest,
    db: Session = Depends(get_db),
) -> IPTVScoutResponse:
    """
    Scout a Telegram group or supergroup for IPTV leads.
    Extracts usernames, timestamps, full message text, auto-translates non-English messages,
    and accurately categorizes buyer intent.
    """
    start_time = time.monotonic()
    raw_link = payload.group_link.strip()
    if not raw_link:
        raise HTTPException(status_code=400, detail="Telegram group link is required.")

    # 1. Verify connected Telegram account
    account = (
        db.query(models.TelegramAccount)
        .filter(models.TelegramAccount.is_connected == True)
        .first()
    )
    if not account or not account.session_string:
        raise HTTPException(
            status_code=401,
            detail="SESSION_MISSING: No active Telegram account connected. Please login in Settings first.",
        )

    service = TelegramService(
        session_string=account.session_string,
        api_id=account.api_id,
        api_hash=account.api_hash,
    )

    try:
        await service.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Telegram: {e}")
        raise HTTPException(
            status_code=500, detail=f"Telegram connection failed: {str(e)}"
        )

    client = service.client
    target_entity = None
    group_title = "Telegram Group"
    group_id = ""
    group_username = None
    error_msg = None

    try:
        # 2. Resolve Group / Channel Entity
        if "t.me/+" in raw_link or "t.me/joinchat/" in raw_link:
            hash_part = (
                raw_link.split("+")[-1]
                if "t.me/+" in raw_link
                else raw_link.split("/")[-1]
            )
            hash_part = hash_part.split("?")[0].strip()

            try:
                invite_res = await client(CheckChatInviteRequest(hash_part))
                if isinstance(invite_res, ChatInviteAlready):
                    target_entity = invite_res.chat
                elif isinstance(invite_res, ChatInvite):
                    import_res = await client(ImportChatInviteRequest(hash_part))
                    if hasattr(import_res, "chats") and import_res.chats:
                        target_entity = import_res.chats[0]
            except errors.UserAlreadyParticipantError:
                dialogs = await client.get_dialogs()
                for d in dialogs:
                    if d.is_group or d.is_channel:
                        target_entity = d.entity
                        break
            except Exception as e:
                logger.warning(f"Invite check/import note: {e}")
                try:
                    import_res = await client(ImportChatInviteRequest(hash_part))
                    if hasattr(import_res, "chats") and import_res.chats:
                        target_entity = import_res.chats[0]
                except errors.UserAlreadyParticipantError:
                    pass
                except Exception as ex2:
                    error_msg = f"Invite link notice: {ex2}"

            if not target_entity:
                try:
                    target_entity = await client.get_entity(raw_link)
                except Exception as ex3:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Could not join or resolve Telegram invite link: {ex3}",
                    )
        else:
            clean_name = (
                raw_link.replace("https://t.me/", "")
                .replace("http://t.me/", "")
                .replace("@", "")
                .split("/")[0]
                .split("?")[0]
                .strip()
            )
            try:
                target_entity = await client.get_entity(clean_name)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not resolve Telegram entity '@{clean_name}': {str(e)}",
                )

            try:
                await client(JoinChannelRequest(target_entity))
            except errors.UserAlreadyParticipantError:
                pass
            except Exception as e:
                logger.info(f"Join group note: {e}")

        group_title = getattr(target_entity, "title", str(getattr(target_entity, "id", "Group")))
        group_id = str(getattr(target_entity, "id", ""))
        group_username = getattr(target_entity, "username", None)

        # 3. Retrieve Messages
        scan_limit = min(max(payload.limit or 200, 10), 1000)
        messages = await client.get_messages(target_entity, limit=scan_limit)

        leads: List[MessageLead] = []
        sender_cache: Dict[str, Dict[str, Any]] = {}
        unique_users = set()
        high_intent_count = 0

        # Custom keywords if provided
        custom_kw_list = (
            [k.strip().lower() for k in payload.custom_keywords.split(",") if k.strip()]
            if payload.custom_keywords
            else []
        )

        async with httpx.AsyncClient() as http_client:
            for msg in messages:
                msg_text = msg.text or msg.message or ""
                if not msg_text.strip():
                    continue

                # Sender lookup (cached for speed)
                sender_id_str = str(msg.sender_id) if msg.sender_id else ""
                if sender_id_str and sender_id_str in sender_cache:
                    s_info = sender_cache[sender_id_str]
                else:
                    s_info = {
                        "username": None,
                        "display_name": "Anonymous / Unknown",
                        "is_bot": False,
                    }
                    try:
                        sender = await msg.get_sender()
                        if sender:
                            if isinstance(sender, User):
                                uname = getattr(sender, "username", None)
                                first = getattr(sender, "first_name", "") or ""
                                last = getattr(sender, "last_name", "") or ""
                                dname = f"{first} {last}".strip() or uname or f"User {sender.id}"
                                s_info = {
                                    "username": uname,
                                    "display_name": dname,
                                    "is_bot": bool(getattr(sender, "bot", False)),
                                }
                            elif isinstance(sender, Channel) or isinstance(sender, Chat):
                                s_info = {
                                    "username": getattr(sender, "username", None),
                                    "display_name": getattr(sender, "title", "Channel"),
                                    "is_bot": False,
                                }
                    except Exception as e:
                        logger.debug(f"Sender lookup note: {e}")

                    if sender_id_str:
                        sender_cache[sender_id_str] = s_info

                # Auto-Translation
                translated_text = None
                detected_lang = None
                is_trans = False

                if payload.auto_translate:
                    translated_text, detected_lang, is_trans = await _translate_to_english(
                        msg_text, http_client
                    )

                # Intent & IPTV analysis on both original and translated text
                is_related, score, category, matched_kws = _analyze_iptv_intent(msg_text)

                if is_trans and translated_text:
                    t_related, t_score, t_category, t_kws = _analyze_iptv_intent(translated_text)
                    if t_related:
                        is_related = True
                        score_rank = {"High": 3, "Medium": 2, "General": 1, "None": 0}
                        if score_rank[t_score] > score_rank[score]:
                            score = t_score
                            category = t_category
                        for tk in t_kws:
                            if tk.lower() not in [k.lower() for k in matched_kws]:
                                matched_kws.append(tk)

                # Check custom keywords
                if custom_kw_list:
                    texts_to_check = [msg_text.lower()]
                    if translated_text:
                        texts_to_check.append(translated_text.lower())
                    for text_version in texts_to_check:
                        for ckw in custom_kw_list:
                            if ckw in text_version and ckw not in [k.lower() for k in matched_kws]:
                                matched_kws.append(ckw)
                                is_related = True
                                if score == "None":
                                    score = "Medium"
                                    category = f"Custom Match: '{ckw}'"

                # Filter if requested
                if payload.filter_iptv_only and not is_related:
                    continue

                if score == "High":
                    high_intent_count += 1

                if s_info["username"]:
                    unique_users.add(s_info["username"].lower())
                elif sender_id_str:
                    unique_users.add(sender_id_str)

                # Format timestamp
                date_obj = msg.date
                date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                date_iso = date_obj.isoformat()

                leads.append(
                    MessageLead(
                        message_id=msg.id,
                        sender_id=sender_id_str or None,
                        username=s_info["username"],
                        display_name=s_info["display_name"],
                        is_bot=s_info["is_bot"],
                        date_str=date_str,
                        date_iso=date_iso,
                        message_text=msg_text.strip(),
                        translated_text=translated_text if is_trans else None,
                        detected_language=detected_lang,
                        is_translated=is_trans,
                        is_iptv_related=is_related,
                        relevance_score=score,
                        intent_category=category,
                        matched_keywords=matched_kws,
                    )
                )

        duration = round(time.monotonic() - start_time, 2)

        return IPTVScoutResponse(
            group_link=raw_link,
            group_title=group_title,
            group_id=group_id,
            group_username=group_username,
            total_scanned=len(messages),
            total_leads=len(leads),
            high_intent_count=high_intent_count,
            unique_users_count=len(unique_users),
            scan_duration_seconds=duration,
            leads=leads,
            error=error_msg,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Group scout error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to scout Telegram group: {str(e)}"
        )
    finally:
        await service.disconnect()
