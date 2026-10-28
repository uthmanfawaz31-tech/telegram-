import asyncio
from datetime import datetime
import json
import logging
import os
import random
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db, SessionLocal
from app.models import models
from app.schemas import schemas
from app.services.telegram_service import TelegramService

router = APIRouter()
logger = logging.getLogger(__name__)

# Active background worker and heartbeat tracking
active_workers: Set[int] = set()
worker_heartbeat: Dict[int, float] = {}

async def send_keep_alive_ping():
    """
    Pings the server's public URL (Render or local) every 3.5 minutes
    so Render Free tier NEVER spins down or terminates during an outreach campaign!
    """
    public_url = os.getenv("RENDER_EXTERNAL_URL", "https://telepro-back.onrender.com").rstrip("/")
    ping_url = f"{public_url}/api/v1/ping"
    try:
        req = urllib.request.Request(ping_url, headers={"User-Agent": "TelePro-KeepAlive/1.0"})
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10))
        logger.info(f"Keep-alive self-ping sent to {ping_url}")
    except Exception as e:
        logger.debug(f"Keep-alive ping notice: {e}")

@router.get("/ping")
def ping_endpoint() -> dict:
    """
    Lightweight keep-alive endpoint used by workers and frontends to prevent cloud container sleep.
    """
    return {
        "status": "pong",
        "active_workers": list(active_workers),
        "timestamp": datetime.utcnow().isoformat()
    }

async def run_broadcast_worker(
    campaign_id: int,
    session_string: str,
    targets: List[dict], # list of {"id": str, "name": str}
    message_text: str,
    delay_seconds: int = 25,
    use_jitter: bool = True,
    api_id: Optional[str] = None,
    api_hash: Optional[str] = None,
    media_path: Optional[str] = None,
    media_url: Optional[str] = None
):
    """
    Resilient stateful broadcast worker capable of handling 300+ groups safely:
    - Timing: Flexible configurable interval (Turbo 10s, Balanced 25s, Safe 60s).
    - Media: Supports uploading image/video along with text caption!
    - Anti-Sleep: Self-pings public URL so Render/cloud servers NEVER sleep while broadcasting!
    - Anti-Spam: Dynamic spintax, human typing simulation, and Telegram FloodWait auto-recovery.
    - Stateful & Resilient: Auto-reconnects on network drops, non-blocking pause/resume, and exact position recovery.
    """
    active_workers.add(campaign_id)
    worker_heartbeat[campaign_id] = time.time()
    last_keepalive_time = time.time()
    db = SessionLocal()
    service = TelegramService(session_string=session_string, api_id=api_id, api_hash=api_hash)
    
    try:
        campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
        if not campaign:
            return

        campaign.status = "running"
        if not campaign.started_at:
            campaign.started_at = datetime.utcnow()
        campaign.total_targets = len(targets)
        db.commit()

        await service.connect()

        # Send initial keep-alive ping right at start
        await send_keep_alive_ping()

        # Ensure media is locally cached on disk once for zero-drop delivery across all 300+ targets
        local_media_path = None
        target_media = campaign.media_path or media_path
        target_url = campaign.media_url or media_url

        if target_media and os.path.exists(target_media):
            local_media_path = target_media
        elif target_url and target_url.startswith("data:"):
            try:
                import base64
                from app.api.api_v1.endpoints.media import UPLOAD_DIR
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                ext = ".jpg" if "image" in target_url[:30] else ".mp4"
                save_path = os.path.join(UPLOAD_DIR, f"campaign_{campaign_id}{ext}")
                _, b64 = target_url.split(",", 1) if "," in target_url else ("", target_url)
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                local_media_path = save_path
            except Exception as pe:
                logger.warning(f"Could not cache base64 media locally: {pe}")
        elif target_url and (target_url.startswith("http://") or target_url.startswith("https://")):
            try:
                from app.api.api_v1.endpoints.media import UPLOAD_DIR
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                fname = target_url.rstrip("/").split("/")[-1].split("?")[0]
                local_candidate = os.path.join(UPLOAD_DIR, fname)
                if os.path.exists(local_candidate):
                    local_media_path = local_candidate
                else:
                    import urllib.request
                    save_path = os.path.join(UPLOAD_DIR, f"cached_{campaign_id}_{fname}")
                    urllib.request.urlretrieve(target_url, save_path)
                    if os.path.exists(save_path):
                        local_media_path = save_path
            except Exception as ue:
                logger.warning(f"Could not download remote media locally: {ue}")

        for idx in range(campaign.current_index, len(targets)):
            target = targets[idx]
            chat_id = target["id"]
            chat_title = target.get("name") or f"Group {chat_id}"
            worker_heartbeat[campaign_id] = time.time()

            # Check campaign status (pause or cancel)
            while True:
                try:
                    db.refresh(campaign)
                    if campaign.status in ("cancelled", "paused", "interrupted"):
                        logger.info(f"Broadcast {campaign_id} status is '{campaign.status}'. Stopping worker.")
                        return
                except Exception as dbe:
                    logger.warning(f"DB status check notice: {dbe}")
                break

            # Update current progress in database
            campaign.current_index = idx
            campaign.current_target_name = chat_title
            try:
                db.commit()
            except Exception:
                db.rollback()

            # Dynamic typing duration based on user pacing
            typing_dur = 1.0 if delay_seconds <= 15 else 2.5

            # Send message with anti-spam safeguards (typing simulation, spintax, variables, media)
            try:
                success, sent_content, err_msg = await service.send_humanized_message(
                    peer_id=chat_id,
                    template_text=campaign.message_text or message_text,
                    group_name=chat_title,
                    simulate_typing=True,
                    typing_duration=typing_dur,
                    media_path=local_media_path,
                    media_url=None if local_media_path else (campaign.media_url or media_url)
                )
            except Exception as send_err:
                logger.error(f"Error in send_humanized_message for {chat_id} ({chat_title}): {send_err}")
                success = False
                sent_content = None
                err_msg = str(send_err)

            # Record log
            try:
                log = models.BroadcastLog(
                    campaign_id=campaign_id,
                    group_id=str(chat_id),
                    group_name=chat_title,
                    status="success" if success else "failed",
                    error_message=err_msg,
                    sent_message_snippet=sent_content[:200] if sent_content else None,
                    sent_at=datetime.utcnow()
                )
                db.add(log)

                campaign.processed_count += 1
                if success:
                    campaign.success_count += 1
                else:
                    campaign.failed_count += 1
                db.commit()
            except Exception as log_err:
                logger.warning(f"Error saving log: {log_err}")
                db.rollback()

            # Check if keepalive ping is due (every 3.5 minutes) to keep Render awake
            now = time.time()
            if now - last_keepalive_time > 210:
                await send_keep_alive_ping()
                last_keepalive_time = now

            # Pacing timing: wait before the next group
            if idx < len(targets) - 1:
                base_delay = delay_seconds if (delay_seconds is not None and delay_seconds >= 3) else 25
                if use_jitter:
                    jitter_range = min(4, max(1, int(base_delay * 0.15)))
                    min_delay = max(2.0, float(base_delay - jitter_range))
                    max_delay = float(base_delay + jitter_range + 1)
                    wait_time = random.uniform(min_delay, max_delay)
                else:
                    wait_time = float(base_delay)

                logger.info(f"Target {idx + 1}/{len(targets)} sent. Waiting {wait_time:.1f}s before next group...")
                
                # Sleep in 2-second increments so user pause/cancel is responsive and DB is checked gently
                remaining = wait_time
                while remaining > 0:
                    step = min(remaining, 2.5)
                    await asyncio.sleep(step)
                    remaining -= step
                    worker_heartbeat[campaign_id] = time.time()
                    try:
                        db.refresh(campaign)
                        if campaign.status in ("cancelled", "paused", "interrupted"):
                            break
                    except Exception:
                        pass

        try:
            db.refresh(campaign)
            if campaign.status != "cancelled":
                campaign.status = "completed"
                campaign.completed_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()

    except Exception as e:
        import traceback
        logger.error(f"Broadcast worker error in campaign {campaign_id}: {traceback.format_exc()}")
        try:
            db.refresh(campaign)
            campaign.status = "interrupted"
            db.commit()
        except Exception:
            pass
    finally:
        active_workers.discard(campaign_id)
        worker_heartbeat.pop(campaign_id, None)
        await service.disconnect()
        db.close()

@router.post("/", response_model=schemas.CampaignResponse)
async def create_campaign(
    payload: schemas.CampaignCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Create and launch a broadcast campaign.
    Defaults to 60s (1 minute) interval between groups to prevent spam detection.
    Stores target list permanently so it can resume after server restart or internet drop!
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account or not account.session_string:
        raise HTTPException(status_code=400, detail="No connected Telegram account found. Please connect in Settings.")

    targets = []
    if payload.chat_ids and len(payload.chat_ids) > 0:
        requested_ids = [str(cid).strip() for cid in payload.chat_ids]
        groups = db.query(models.TelegramGroup).filter(
            models.TelegramGroup.account_phone == account.phone,
            models.TelegramGroup.peer_id.in_(requested_ids)
        ).all()
        title_map = {g.peer_id: g.title for g in groups}
        for cid in requested_ids:
            targets.append({
                "id": cid,
                "name": title_map.get(cid, f"Group {cid}")
            })
    else:
        groups = db.query(models.TelegramGroup).filter(
            models.TelegramGroup.account_phone == account.phone,
            models.TelegramGroup.is_active == True,
            models.TelegramGroup.can_send_messages == True
        ).all()
        for g in groups:
            targets.append({
                "id": g.peer_id,
                "name": g.title
            })

    if not targets:
        raise HTTPException(
            status_code=400,
            detail="No target groups selected or found. Please sync groups first."
        )

    delay_sec = payload.delay_seconds if (payload.delay_seconds is not None and payload.delay_seconds >= 3) else 25

    # Sanitize message text to strip any tags accidentally glued to link slugs
    clean_message = payload.message_text.strip()
    while re.search(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', clean_message):
        clean_message = re.sub(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', r'\1', clean_message)

    clean_media_path = payload.media_path.strip() if payload.media_path else None
    clean_media_url = payload.media_url.strip() if payload.media_url else None

    db_campaign = models.Campaign(
        name=payload.name.strip(),
        message_text=clean_message,
        scheduled_at=payload.scheduled_at,
        status="pending",
        total_targets=len(targets),
        processed_count=0,
        success_count=0,
        failed_count=0,
        current_index=0,
        delay_seconds=delay_sec,
        use_jitter=bool(payload.use_jitter),
        target_chat_ids=json.dumps(targets),
        media_path=clean_media_path,
        media_url=clean_media_url,
        created_at=datetime.utcnow()
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)

    # Launch background broadcast worker
    background_tasks.add_task(
        run_broadcast_worker,
        db_campaign.id,
        account.session_string,
        targets,
        clean_message,
        delay_sec,
        bool(payload.use_jitter),
        account.api_id,
        account.api_hash,
        clean_media_path,
        clean_media_url
    )

    return db_campaign

@router.get("/", response_model=List[schemas.CampaignResponse])
def list_campaigns(
    limit: int = Query(50),
    offset: int = Query(0),
    db: Session = Depends(get_db)
) -> Any:
    """
    List campaigns with real-time status.
    Auto-detects interrupted campaigns safely without terminating active workers.
    """
    campaigns = db.query(models.Campaign).order_by(models.Campaign.created_at.desc()).offset(offset).limit(limit).all()
    
    now = time.time()
    for c in campaigns:
        last_hb = worker_heartbeat.get(c.id, 0)
        # Only mark as interrupted if definitely not active and heartbeat has been dead for > 180 seconds
        if c.status == "running" and c.id not in active_workers and (now - last_hb > 180):
            c.status = "interrupted"
            db.commit()

    return campaigns

@router.get("/{campaign_id}", response_model=schemas.CampaignResponse)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Any:
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    now = time.time()
    last_hb = worker_heartbeat.get(campaign.id, 0)
    if campaign.status == "running" and campaign.id not in active_workers and (now - last_hb > 180):
        campaign.status = "interrupted"
        db.commit()
    return campaign

@router.patch("/{campaign_id}", response_model=schemas.CampaignResponse)
def update_campaign(
    campaign_id: int,
    payload: schemas.CampaignUpdate,
    db: Session = Depends(get_db)
) -> Any:
    """
    Update campaign details (e.g. edit message text, fix links, or update delay).
    """
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if payload.name is not None:
        campaign.name = payload.name.strip()
    if payload.message_text is not None:
        clean_msg = payload.message_text.strip()
        while re.search(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', clean_msg):
            clean_msg = re.sub(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', r'\1', clean_msg)
        campaign.message_text = clean_msg
    if payload.delay_seconds is not None:
        campaign.delay_seconds = max(3, payload.delay_seconds)
    if payload.media_path is not None:
        campaign.media_path = payload.media_path.strip() if payload.media_path else None
    if payload.media_url is not None:
        campaign.media_url = payload.media_url.strip() if payload.media_url else None

    db.commit()
    db.refresh(campaign)
    return campaign

@router.post("/{campaign_id}/pause", response_model=schemas.CampaignResponse)
def pause_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Any:
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "paused"
    db.commit()
    db.refresh(campaign)
    return campaign

@router.post("/{campaign_id}/resume", response_model=schemas.CampaignResponse)
async def resume_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Resume an interrupted or paused campaign from the exact target it stopped at!
    Automatically cleans any accidental tags glued onto links before launching.
    """
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account or not account.session_string:
        raise HTTPException(status_code=400, detail="Telegram account not connected")

    # Sanitize campaign message so no link is ever broken
    if campaign.message_text:
        clean_msg = campaign.message_text
        while re.search(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', clean_msg):
            clean_msg = re.sub(r'(https?://[^\s{}]+)\{[a-zA-Z0-9_| ]+\}', r'\1', clean_msg)
        campaign.message_text = clean_msg

    campaign.status = "running"
    db.commit()
    db.refresh(campaign)

    # If worker is NOT running in background, re-launch it with saved targets!
    if campaign.id not in active_workers:
        try:
            targets = json.loads(campaign.target_chat_ids) if campaign.target_chat_ids else []
        except Exception:
            targets = []

        if not targets:
            # Reconstruct from groups
            groups = db.query(models.TelegramGroup).filter(
                models.TelegramGroup.account_phone == account.phone,
                models.TelegramGroup.is_active == True,
                models.TelegramGroup.can_send_messages == True
            ).all()
            targets = [{"id": g.peer_id, "name": g.title} for g in groups]

        background_tasks.add_task(
            run_broadcast_worker,
            campaign.id,
            account.session_string,
            targets,
            campaign.message_text,
            campaign.delay_seconds or 25,
            bool(campaign.use_jitter),
            account.api_id,
            account.api_hash,
            campaign.media_path,
            campaign.media_url
        )

    return campaign

@router.post("/{campaign_id}/stop", response_model=schemas.CampaignResponse)
def stop_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Any:
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "cancelled"
    db.commit()
    db.refresh(campaign)
    return campaign

@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Any:
    """
    Delete a campaign and its delivery logs.
    """
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # If actively running, cancel it first
    campaign.status = "cancelled"
    db.commit()

    db.delete(campaign)
    db.commit()
    return {"msg": "Campaign deleted successfully"}

@router.get("/{campaign_id}/logs", response_model=List[schemas.BroadcastLogResponse])
def get_campaign_logs(
    campaign_id: int,
    limit: int = Query(100),
    db: Session = Depends(get_db)
) -> Any:
    """
    Get group delivery logs for a campaign.
    """
    return db.query(models.BroadcastLog).filter(
        models.BroadcastLog.campaign_id == campaign_id
    ).order_by(models.BroadcastLog.sent_at.desc()).limit(limit).all()
