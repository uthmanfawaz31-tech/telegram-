from fastapi import APIRouter
from app.api.api_v1.endpoints import auth, campaigns, telegram, templates, media, fiverr, iptv_scout

api_router = APIRouter()

@api_router.get("/")
def api_root():
    return {"message": "TelePro Telegram Broadcasting Platform API v1"}

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(media.router, prefix="/media", tags=["media"])
api_router.include_router(fiverr.router, prefix="/fiverr", tags=["fiverr"])
api_router.include_router(iptv_scout.router, prefix="/iptv-scout", tags=["iptv-scout"])

