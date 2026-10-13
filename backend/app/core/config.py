from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Union
from pydantic import field_validator
from dotenv import load_dotenv
import os

# Load .env if present
load_dotenv(os.path.join(os.getcwd(), '.env'), override=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "TelePro - Telegram Broadcasting Platform"
    API_V1_STR: str = "/api/v1"
    
    # DATABASE (SQLite defaults with WAL mode for smooth concurrent access)
    DATABASE_URL: str = "sqlite:///./test.db"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL

    # TELEGRAM CREDENTIALS
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""

    # ANTI-SPAM BROADCAST DEFAULTS
    # Default 60 seconds (1 minute difference between groups)
    DEFAULT_BROADCAST_DELAY_SECONDS: int = 60
    MIN_JITTER_SECONDS: int = 55
    MAX_JITTER_SECONDS: int = 68
    TYPING_SIMULATION_SECONDS: float = 3.5

    # CORS
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if not v or v.strip() == "*":
                return ["*"]
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            cleaned = v.strip().replace('"', "").replace("'", "")
            return [i.strip() for i in cleaned.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
