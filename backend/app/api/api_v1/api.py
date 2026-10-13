from fastapi import APIRouter
from app.api.api_v1.endpoints import auth, campaigns, telegram, templates

api_router = APIRouter()

@api_router.get("/")
def api_root():
    return {"message": "TelePro Telegram Broadcasting Platform API v1"}

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
