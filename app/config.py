from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    webhook_secret: str
    webhook_url: str

    # Database
    database_url: str
    postgres_db: str = "crazydrift"
    postgres_user: str = "cduser"
    postgres_password: str = "password"

    # Redis
    redis_url: str
    redis_password: str = ""

    # Anthropic
    anthropic_api_key: str = ""

    # Admin
    admin_login: str = "CrazyAdmin"
    admin_password: str = "admin123"
    admin_recovery_secret: str = "recovery_secret"

    # App
    secret_key: str = "secret_key_change_in_production"
    debug: bool = False
    allowed_hosts: str = "localhost"

    # Materials
    materials_about_url: str = "https://crazydrift.ru/about"
    materials_presentation_url: str = "https://crazydrift.ru/presentation.pdf"
    materials_financial_url: str = "https://crazydrift.ru/financial.pdf"
    materials_site_url: str = "https://crazydrift.ru"
    materials_youtube_url: str = "https://youtube.com/@crazydrift"
    materials_manager_url: str = "https://t.me/crazydrift_manager"
    manager_chat_id: int = 0  # Telegram ID менеджера для уведомлений

    # Антикризисный советник (bot2)
    ak_bot_token: str = ""
    ak_webhook_url: str = ""
    ak_webhook_secret: str = "ak_secret_change_me"

    class Config:
        extra = "ignore"
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
