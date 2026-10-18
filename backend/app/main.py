from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.api_v1.api import api_router
from app.core.config import settings
from app.core.db import init_db

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

import asyncio
import os
import urllib.request
import logging

logger = logging.getLogger(__name__)

async def render_keep_alive_loop():
    """Background loop that pings the public URL every 4 minutes whenever a campaign is active to prevent cloud container sleep."""
    while True:
        await asyncio.sleep(210)
        try:
            from app.api.api_v1.endpoints.campaigns import active_workers
            if active_workers:
                public_url = os.getenv("RENDER_EXTERNAL_URL", "https://telepro-back.onrender.com").rstrip("/")
                ping_url = f"{public_url}/api/v1/ping"
                loop = asyncio.get_event_loop()
                req = urllib.request.Request(ping_url, headers={"User-Agent": "TelePro-Monitor/1.0"})
                await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10))
                logger.info(f"Keep-alive monitor pinged {ping_url} (Active workers: {len(active_workers)})")
        except Exception as e:
            logger.debug(f"Keep-alive loop notice: {e}")

@app.on_event("startup")
def on_startup():
    init_db()
    asyncio.create_task(render_keep_alive_loop())

# Enable unrestricted CORS so any frontend (Vercel, custom domain, localhost) connects without 'Failed to fetch'
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "TelePro Telegram Broadcasting Platform API",
        "docs": "/docs"
    }
