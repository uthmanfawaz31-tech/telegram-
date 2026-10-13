import asyncio
from datetime import datetime
import json
import logging
import random
from typing import Any, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db, SessionLocal
from app.models import models
from app.schemas import schemas
from app.services.telegram_service import TelegramService

router = APIRouter()
logger = logging.getLogger(__name__)

# Active background worker tracking
active_workers: Set[int] = set()

async def run_broadcast_worker(
    campaign_id: int,
    session_string: str,
    targets: List[dict], # list of {"id": str, "name": str}
    message_text: str,
    delay_seconds: int = 60,
    use_jitter: bool = True,
    api_id: Optional[str] = None,
    api_hash: Optional[str] = None
):
    """
    Stateful broadcast worker capable of handling 300+ groups safely:
    - Timing: ~60 seconds (1 minute) interval between groups.
    - Anti-Spam: Dynamic spintax, human typing simulation, and Telegram FloodWait auto-recovery.
    - Stateful: Supports pause, resume, and cancellation from frontend in real-time.
    - Resumable: If interrupted by network disconnect, can pick up exactly from current_index!
    """
    active_workers.add(campaign_id)
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

        for idx in range(campaign.current_index, len(targets)):
            target = targets[idx]
            chat_id = target["id"]
            chat_title = target.get("name") or f"Group {chat_id}"

            # Check campaign status (pause or cancel)
            while True:
                db.refresh(campaign)
                if campaign.status == "cancelled":
                    logger.info(f"Broadcast {campaign_id} cancelled.")
                    return
                elif campaign.status in ("paused", "interrupted"):
                    # Wait 5 seconds and check again
                    await asyncio.sleep(5)
                    continue
                break

            # Update current progress in database
            campaign.current_index = idx
            campaign.current_target_name = chat_title
            db.commit()

            # Send message with anti-spam safeguards (typing simulation, spintax, variables)
            success, sent_content, err_msg = await service.send_humanized_message(
                peer_id=chat_id,
                template_text=message_text,
                group_name=chat_title
            )

            # Record log
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

            # Anti-Spam timing: wait approximately 1 minute before the next group
            if idx < len(targets) - 1:
                base_delay = delay_seconds if delay_seconds > 0 else 60
                if use_jitter:
                    min_delay = max(20, base_delay - 5)
                    max_delay = base_delay + 8
                    wait_time = random.uniform(min_delay, max_delay)
                else:
                    wait_time = float(base_delay)

                logger.info(f"Target {idx + 1}/{len(targets)} sent. Waiting {wait_time:.1f}s before next group...")
                
                # Sleep in short increments so user pause/cancel is immediately responsive
                sleep_increments = int(wait_time)
                for _ in range(sleep_increments):
                    db.refresh(campaign)
                    if campaign.status in ("cancelled", "paused", "interrupted"):
                        break
                    await asyncio.sleep(1)

        db.refresh(campaign)
        if campaign.status != "cancelled":
            campaign.status = "completed"
            campaign.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        logger.error(f"Broadcast worker error in campaign {campaign_id}: {e}")
        try:
            db.refresh(campaign)
            campaign.status = "interrupted"
            db.commit()
        except Exception:
            pass
    finally:
        active_workers.discard(campaign_id)
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

    delay_sec = payload.delay_seconds if (payload.delay_seconds is not None and payload.delay_seconds >= 10) else 60

    db_campaign = models.Campaign(
        name=payload.name.strip(),
        message_text=payload.message_text.strip(),
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
        payload.message_text,
        delay_sec,
        bool(payload.use_jitter),
        account.api_id,
        account.api_hash
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
    Auto-detects interrupted campaigns (if server restarted while a campaign was marked running).
    """
    campaigns = db.query(models.Campaign).order_by(models.Campaign.created_at.desc()).offset(offset).limit(limit).all()
    
    # If a campaign is marked 'running' but no background worker is alive, mark as 'interrupted' so user can resume!
    for c in campaigns:
        if c.status == "running" and c.id not in active_workers:
            c.status = "interrupted"
            db.commit()

    return campaigns

@router.get("/{campaign_id}", response_model=schemas.CampaignResponse)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)) -> Any:
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == "running" and campaign.id not in active_workers:
        campaign.status = "interrupted"
        db.commit()
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
    """
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account or not account.session_string:
        raise HTTPException(status_code=400, detail="Telegram account not connected")

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
            campaign.delay_seconds or 60,
            bool(campaign.use_jitter),
            account.api_id,
            account.api_hash
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
