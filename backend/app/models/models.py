from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True)
    session_string = Column(Text, nullable=True)
    api_id = Column(String, nullable=True)
    api_hash = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    telegram_id = Column(String, nullable=True)
    is_connected = Column(Boolean(), default=True)
    last_active_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TelegramGroup(Base):
    __tablename__ = "telegram_groups"
    id = Column(Integer, primary_key=True, index=True)
    account_phone = Column(String, index=True)
    peer_id = Column(String, index=True)
    title = Column(String)
    username = Column(String, nullable=True)
    entity_type = Column(String, default="group") # group, supergroup, channel
    members_count = Column(Integer, default=0)
    can_send_messages = Column(Boolean(), default=True)
    is_active = Column(Boolean(), default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_synced_at = Column(DateTime, default=datetime.datetime.utcnow)

class BroadcastTemplate(Base):
    __tablename__ = "broadcast_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    message_text = Column(Text, nullable=False)
    tags = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    message_text = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending") # pending, running, paused, completed, cancelled, failed
    total_targets = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    current_target_name = Column(String, nullable=True)
    current_index = Column(Integer, default=0)
    delay_seconds = Column(Integer, default=60) # 1-minute default timing
    use_jitter = Column(Boolean, default=True) # human-like timing jitter
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    logs = relationship("BroadcastLog", back_populates="campaign", cascade="all, delete-orphan")

class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    group_id = Column(String)
    group_name = Column(String, nullable=True)
    status = Column(String) # success, failed, skipped, flood_wait
    error_message = Column(Text, nullable=True)
    sent_message_snippet = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)

    campaign = relationship("Campaign", back_populates="logs")
