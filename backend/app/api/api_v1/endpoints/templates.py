from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, List
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.db import get_db
from app.models import models
from app.schemas import schemas
from app.services.telegram_service import TelegramService

router = APIRouter()

@router.get("/", response_model=List[schemas.BroadcastTemplateResponse])
def list_templates(db: Session = Depends(get_db)) -> Any:
    """
    List all saved message templates.
    """
    return db.query(models.BroadcastTemplate).order_by(models.BroadcastTemplate.updated_at.desc()).all()

@router.post("/", response_model=schemas.BroadcastTemplateResponse)
def create_template(
    payload: schemas.BroadcastTemplateCreate,
    db: Session = Depends(get_db)
) -> Any:
    """
    Create a new message template.
    """
    template = models.BroadcastTemplate(
        name=payload.name.strip(),
        message_text=payload.message_text.strip(),
        tags=payload.tags.strip() if payload.tags else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template

@router.get("/{template_id}", response_model=schemas.BroadcastTemplateResponse)
def get_template(template_id: int, db: Session = Depends(get_db)) -> Any:
    template = db.query(models.BroadcastTemplate).filter(models.BroadcastTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template

@router.put("/{template_id}", response_model=schemas.BroadcastTemplateResponse)
def update_template(
    template_id: int,
    payload: schemas.BroadcastTemplateUpdate,
    db: Session = Depends(get_db)
) -> Any:
    template = db.query(models.BroadcastTemplate).filter(models.BroadcastTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if payload.name is not None:
        template.name = payload.name.strip()
    if payload.message_text is not None:
        template.message_text = payload.message_text.strip()
    if payload.tags is not None:
        template.tags = payload.tags.strip()
    template.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(template)
    return template

@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)) -> Any:
    template = db.query(models.BroadcastTemplate).filter(models.BroadcastTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()
    return {"msg": "Template deleted successfully"}

@router.post("/preview", response_model=schemas.TemplatePreviewResponse)
def preview_template(payload: schemas.TemplatePreviewRequest) -> Any:
    """
    Test and preview multiple spintax variations of a template message.
    """
    samples = []
    sample_group_names = [
        "Crypto Alpha Traders",
        "Global Tech Innovations",
        "E-Commerce Growth Hub",
        "Web3 Builders Community",
        "Digital Marketing Experts"
    ]
    
    count = min(max(payload.count or 3, 1), 5)
    for i in range(count):
        grp_name = sample_group_names[i % len(sample_group_names)]
        variant = TelegramService.render_template(payload.template_text, group_name=grp_name)
        samples.append(variant)

    return {"samples": samples}
