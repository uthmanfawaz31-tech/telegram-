from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# --- Telegram Account Schemas ---
class TelegramConfigUpdate(BaseModel):
    api_id: str
    api_hash: str

class SendCodeRequest(BaseModel):
    phone: str
    api_id: Optional[str] = None
    api_hash: Optional[str] = None

class LoginRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str
    password: Optional[str] = None # For 2FA if enabled

class TwoFactorRequest(BaseModel):
    phone: str
    password: str

class RestoreSessionRequest(BaseModel):
    session_string: str
    phone: Optional[str] = None
    api_id: Optional[str] = None
    api_hash: Optional[str] = None

class TelegramAccountResponse(BaseModel):
    id: int
    phone: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    telegram_id: Optional[str] = None
    api_id: Optional[str] = None
    is_connected: bool
    last_active_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Telegram Group Schemas ---
class TelegramGroupResponse(BaseModel):
    id: int
    peer_id: str
    title: str
    username: Optional[str] = None
    entity_type: str
    members_count: int
    can_send_messages: bool
    is_active: bool
    last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SyncGroupsResponse(BaseModel):
    total_groups: int
    new_groups: int
    updated_groups: int
    synced_at: datetime

# --- Template Schemas ---
class BroadcastTemplateBase(BaseModel):
    name: str
    message_text: str
    tags: Optional[str] = None

class BroadcastTemplateCreate(BroadcastTemplateBase):
    pass

class BroadcastTemplateUpdate(BaseModel):
    name: Optional[str] = None
    message_text: Optional[str] = None
    tags: Optional[str] = None

class BroadcastTemplateResponse(BroadcastTemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TemplatePreviewRequest(BaseModel):
    template_text: str
    count: Optional[int] = 3

class TemplatePreviewResponse(BaseModel):
    samples: List[str]

# --- Campaign Schemas ---
class BroadcastLogResponse(BaseModel):
    id: int
    group_id: str
    group_name: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    sent_message_snippet: Optional[str] = None
    sent_at: datetime

    class Config:
        from_attributes = True

class CampaignCreate(BaseModel):
    name: str
    message_text: str
    chat_ids: Optional[List[str]] = None # string peer_ids or group IDs
    delay_seconds: Optional[int] = 60 # 1 minute default delay
    use_jitter: Optional[bool] = True
    scheduled_at: Optional[datetime] = None

class CampaignResponse(BaseModel):
    id: int
    name: str
    message_text: str
    status: str
    total_targets: int
    processed_count: int
    success_count: int
    failed_count: int
    current_target_name: Optional[str] = None
    current_index: int
    delay_seconds: int
    use_jitter: bool
    target_chat_ids: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    logs: Optional[List[BroadcastLogResponse]] = None

    class Config:
        from_attributes = True
