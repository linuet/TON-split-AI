from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "receipts").mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TON Split AI"
    debug: bool = False

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1", alias="OPENAI_MODEL")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db", alias="DATABASE_URL")
    ton_receiver_address: str = Field(
        default="EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",
        alias="TON_RECEIVER_ADDRESS",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8080

    storage_dir: Path = DATA_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()
