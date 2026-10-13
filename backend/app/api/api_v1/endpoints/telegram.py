from fastapi import APIRouter, Depends, HTTPException, Body, Query, BackgroundTasks
from typing import Any, List, Optional
from datetime import datetime
import logging
from telethon import errors

from app.services.telegram_service import TelegramService
from app.core.config import settings
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models import models
from app.schemas import schemas

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory dictionary for active Telegram services during OTP / 2FA flow
active_services = {}

def get_service_for_phone(phone: str, api_id: Optional[str] = None, api_hash: Optional[str] = None) -> TelegramService:
    if phone not in active_services:
        active_services[phone] = TelegramService(api_id=api_id, api_hash=api_hash)
    return active_services[phone]

async def sync_groups_for_account(session_string: str, phone: str, db: Session, api_id: Optional[str] = None, api_hash: Optional[str] = None):
    """
    Helper function to sync groups into database
    """
    service = TelegramService(session_string=session_string, api_id=api_id, api_hash=api_hash)
    try:
        dialogs = await service.get_dialogs()
        new_count = 0
        updated_count = 0
        current_peer_ids = set()

        for d in dialogs:
            peer_id = str(d["peer_id"])
            current_peer_ids.add(peer_id)
            
            existing = db.query(models.TelegramGroup).filter(
                models.TelegramGroup.account_phone == phone,
                models.TelegramGroup.peer_id == peer_id
            ).first()

            if not existing:
                new_group = models.TelegramGroup(
                    account_phone=phone,
                    peer_id=peer_id,
                    title=d["title"],
                    username=d["username"],
                    entity_type=d["entity_type"],
                    members_count=d["members_count"],
                    can_send_messages=d["can_send_messages"],
                    is_active=True,
                    last_synced_at=datetime.utcnow()
                )
                db.add(new_group)
                new_count += 1
            else:
                existing.title = d["title"]
                existing.username = d["username"]
                existing.entity_type = d["entity_type"]
                existing.members_count = d["members_count"]
                existing.can_send_messages = d["can_send_messages"]
                existing.is_active = True
                existing.last_synced_at = datetime.utcnow()
                updated_count += 1

        db.commit()
        return len(dialogs), new_count, updated_count
    except Exception as e:
        logger.error(f"Sync groups error: {e}")
        raise e
    finally:
        await service.disconnect()

@router.get("/account")
def get_account_status(db: Session = Depends(get_db)) -> Any:
    """
    Get active Telegram account status and basic stats.
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account:
        return {
            "is_connected": False,
            "account": None,
            "total_groups": 0
        }
    
    total_groups = db.query(models.TelegramGroup).filter(
        models.TelegramGroup.account_phone == account.phone,
        models.TelegramGroup.is_active == True
    ).count()

    return {
        "is_connected": True,
        "account": {
            "id": account.id,
            "phone": account.phone,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "username": account.username,
            "telegram_id": account.telegram_id,
            "api_id": account.api_id or settings.TELEGRAM_API_ID
        },
        "total_groups": total_groups
    }

@router.post("/send-code")
async def send_code(payload: schemas.SendCodeRequest, db: Session = Depends(get_db)) -> Any:
    """
    Send OTP code to Telegram phone number.
    Accepts custom API ID and Hash if provided.
    """
    phone = payload.phone.strip()
    api_id = payload.api_id.strip() if payload.api_id else settings.TELEGRAM_API_ID
    api_hash = payload.api_hash.strip() if payload.api_hash else settings.TELEGRAM_API_HASH

    # If not passed, check if already stored on account
    if not api_id or not api_hash:
        existing = db.query(models.TelegramAccount).filter(models.TelegramAccount.phone == phone).first()
        if existing and existing.api_id and existing.api_hash:
            api_id = existing.api_id
            api_hash = existing.api_hash

    if not api_id or not api_hash:
        raise HTTPException(
            status_code=400, 
            detail="TELEGRAM_CREDENTIALS_REQUIRED: Please enter your Telegram API ID and API Hash (from my.telegram.org)."
        )

    try:
        # Reset any previous session for this phone to start fresh
        active_services.pop(phone, None)
        service = get_service_for_phone(phone, api_id=api_id, api_hash=api_hash)
        result = await service.send_otp(phone)
        return {
            "msg": "Verification code sent to Telegram app/SMS",
            "phone_code_hash": result.phone_code_hash
        }
    except Exception as e:
        active_services.pop(phone, None)
        logger.error(f"Send OTP error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def telegram_login(
    payload: schemas.LoginRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Login with OTP code. Handles 2FA password prompt if enabled.
    """
    phone = payload.phone.strip()
    service = active_services.get(phone)
    if not service:
        # Fallback to configured settings
        service = get_service_for_phone(phone)

    try:
        user, session_str = await service.sign_in(
            phone=phone, 
            code=payload.code.strip(), 
            phone_code_hash=payload.phone_code_hash.strip(),
            password=payload.password
        )

        # Upsert account in DB
        account = db.query(models.TelegramAccount).filter(models.TelegramAccount.phone == phone).first()
        if not account:
            account = models.TelegramAccount(
                phone=phone,
                session_string=session_str,
                api_id=str(service.api_id) if service.api_id else settings.TELEGRAM_API_ID,
                api_hash=service.api_hash or settings.TELEGRAM_API_HASH,
                first_name=getattr(user, 'first_name', None),
                last_name=getattr(user, 'last_name', None),
                username=getattr(user, 'username', None),
                telegram_id=str(getattr(user, 'id', '')),
                is_connected=True,
                last_active_at=datetime.utcnow()
            )
            db.add(account)
        else:
            account.session_string = session_str
            account.first_name = getattr(user, 'first_name', account.first_name)
            account.last_name = getattr(user, 'last_name', account.last_name)
            account.username = getattr(user, 'username', account.username)
            account.telegram_id = str(getattr(user, 'id', account.telegram_id or ''))
            account.is_connected = True
            account.last_active_at = datetime.utcnow()
            if service.api_id:
                account.api_id = str(service.api_id)
            if service.api_hash:
                account.api_hash = service.api_hash

        db.commit()

        # Clean up temporary active service
        active_services.pop(phone, None)

        # Trigger initial group sync in background
        background_tasks.add_task(
            sync_groups_for_account,
            session_str,
            phone,
            db,
            account.api_id,
            account.api_hash
        )

        return {
            "msg": "Login successful",
            "user": {
                "id": getattr(user, 'id', None),
                "first_name": getattr(user, 'first_name', None),
                "username": getattr(user, 'username', None),
            },
            "session_string": session_str
        }

    except errors.SessionPasswordNeededError:
        return {
            "status": "2fa_required",
            "msg": "Two-Step Verification password is required for this account."
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/2fa")
async def verify_2fa(
    payload: schemas.TwoFactorRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Any:
    """
    Verify 2FA password after OTP code.
    """
    phone = payload.phone.strip()
    service = active_services.get(phone)
    if not service:
        raise HTTPException(status_code=400, detail="Login session expired. Please start login again.")

    try:
        user, session_str = await service.sign_in_password(payload.password)

        account = db.query(models.TelegramAccount).filter(models.TelegramAccount.phone == phone).first()
        if not account:
            account = models.TelegramAccount(
                phone=phone,
                session_string=session_str,
                api_id=str(service.api_id) if service.api_id else settings.TELEGRAM_API_ID,
                api_hash=service.api_hash or settings.TELEGRAM_API_HASH,
                first_name=getattr(user, 'first_name', None),
                username=getattr(user, 'username', None),
                telegram_id=str(getattr(user, 'id', '')),
                is_connected=True,
                last_active_at=datetime.utcnow()
            )
            db.add(account)
        else:
            account.session_string = session_str
            account.is_connected = True
            account.first_name = getattr(user, 'first_name', account.first_name)
            account.username = getattr(user, 'username', account.username)
            account.last_active_at = datetime.utcnow()

        db.commit()
        active_services.pop(phone, None)

        background_tasks.add_task(
            sync_groups_for_account,
            session_str,
            phone,
            db,
            account.api_id,
            account.api_hash
        )

        return {
            "msg": "Login successful",
            "user": {
                "id": getattr(user, 'id', None),
                "first_name": getattr(user, 'first_name', None),
                "username": getattr(user, 'username', None),
            },
            "session_string": session_str
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/disconnect")
def disconnect_account(db: Session = Depends(get_db)) -> Any:
    """
    Disconnect active Telegram session.
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if account:
        account.is_connected = False
        db.commit()
    return {"msg": "Disconnected successfully"}

@router.get("/groups", response_model=List[schemas.TelegramGroupResponse])
def get_groups(
    search: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    can_send_only: Optional[bool] = Query(False),
    limit: Optional[int] = Query(1000), # Accommodates 300+ groups smoothly
    offset: Optional[int] = Query(0),
    db: Session = Depends(get_db)
) -> Any:
    """
    Fetch detected Telegram groups and channels from DB cache.
    Fast and scalable for 300+ groups with instant filtering.
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account:
        raise HTTPException(status_code=401, detail="SESSION_MISSING: No active Telegram account connected.")

    query = db.query(models.TelegramGroup).filter(
        models.TelegramGroup.account_phone == account.phone,
        models.TelegramGroup.is_active == True
    )

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.filter(models.TelegramGroup.title.ilike(search_filter))

    if entity_type and entity_type != "all":
        query = query.filter(models.TelegramGroup.entity_type == entity_type)

    if can_send_only:
        query = query.filter(models.TelegramGroup.can_send_messages == True)

    groups = query.order_by(models.TelegramGroup.title.asc()).offset(offset).limit(limit).all()
    return groups

@router.post("/sync-groups", response_model=schemas.SyncGroupsResponse)
async def sync_groups(db: Session = Depends(get_db)) -> Any:
    """
    Auto-detect and sync all groups from Telegram.
    Updates group list whenever user joins or is added to new groups.
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account or not account.session_string:
        raise HTTPException(status_code=401, detail="SESSION_MISSING: No connected Telegram account found.")

    try:
        total, new_cnt, upd_cnt = await sync_groups_for_account(
            session_string=account.session_string,
            phone=account.phone,
            db=db,
            api_id=account.api_id,
            api_hash=account.api_hash
        )
        return {
            "total_groups": total,
            "new_groups": new_cnt,
            "updated_groups": upd_cnt,
            "synced_at": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to sync groups: {str(e)}")

@router.post("/join")
async def join_group(
    group_link: str = Body(..., embed=True),
    db: Session = Depends(get_db)
) -> Any:
    """
    Join a Telegram group or channel by invite link or username,
    and automatically add it to the user's groups list.
    """
    account = db.query(models.TelegramAccount).filter(models.TelegramAccount.is_connected == True).first()
    if not account or not account.session_string:
        raise HTTPException(status_code=401, detail="SESSION_MISSING: No connected Telegram account found.")

    service = TelegramService(
        session_string=account.session_string,
        api_id=account.api_id,
        api_hash=account.api_hash
    )
    try:
        result = await service.join_group(group_link)
        
        # Immediately save joined group into DB
        if result.get("peer_id"):
            peer_id = result["peer_id"]
            existing = db.query(models.TelegramGroup).filter(
                models.TelegramGroup.account_phone == account.phone,
                models.TelegramGroup.peer_id == peer_id
            ).first()
            if not existing:
                new_grp = models.TelegramGroup(
                    account_phone=account.phone,
                    peer_id=peer_id,
                    title=result.get("title", "Joined Group"),
                    entity_type=result.get("entity_type", "group"),
                    can_send_messages=True,
                    is_active=True,
                    last_synced_at=datetime.utcnow()
                )
                db.add(new_grp)
                db.commit()

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to join group: {str(e)}")
    finally:
        await service.disconnect()
