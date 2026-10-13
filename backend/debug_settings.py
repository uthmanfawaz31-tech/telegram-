import sys
import os
from dotenv import load_dotenv

sys.path.append(os.getcwd())

# Manually load .env to see what's happening
print(f"Loading .env from: {os.path.join(os.getcwd(), '.env')}")
load_dotenv(override=True)

from app.core.config import settings

print("--- DEBUG SETTINGS WITH DOTENV ---")
print(f"ENV TELEGRAM_API_ID: '{os.getenv('TELEGRAM_API_ID')}'")
print(f"ENV TELEGRAM_API_HASH: '{os.getenv('TELEGRAM_API_HASH')}'")
print(f"SETTINGS TELEGRAM_API_ID: '{settings.TELEGRAM_API_ID}'")
print(f"SETTINGS TELEGRAM_API_HASH: '{settings.TELEGRAM_API_HASH}'")
