from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1", alias="OPENAI_MODEL")

    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str = Field(alias="DATABASE_URL_SYNC")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    superadmin_telegram_ids: str = Field(default="", alias="SUPERADMIN_TELEGRAM_IDS")

    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")
    app_secret_key: str = Field(alias="APP_SECRET_KEY")

    signing_token_ttl_hours: int = Field(default=24, alias="SIGNING_TOKEN_TTL_HOURS")
    source_file_retention_days: int = Field(default=30, alias="SOURCE_FILE_RETENTION_DAYS")
    timezone: str = Field(default="Asia/Almaty", alias="TIMEZONE")

    libreoffice_path: str = Field(default="soffice", alias="LIBREOFFICE_PATH")
    storage_path: Path = Field(default=Path("./storage"), alias="STORAGE_PATH")

    backup_encryption_key: str = Field(default="", alias="BACKUP_ENCRYPTION_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    contract_city: str = Field(default="г. Талдыкорган", alias="CONTRACT_CITY")
    executor_full_name: str = Field(
        default="Индивидуальный предприниматель Кияшев Жанибек Даулетович",
        alias="EXECUTOR_FULL_NAME",
    )
    executor_brand_name: str = Field(default="ZakonExpert", alias="EXECUTOR_BRAND_NAME")
    executor_display_name: str = Field(default="ИП ZakonExpert", alias="EXECUTOR_DISPLAY_NAME")
    executor_iin: str = Field(default="000725500183", alias="EXECUTOR_IIN")
    executor_address: str = Field(
        default="Республика Казахстан, г. Талдыкорган, ул. Акын Сара, 152",
        alias="EXECUTOR_ADDRESS",
    )
    executor_phone: str = Field(default="+7 705 876 27 95", alias="EXECUTOR_PHONE")
    executor_kaspi_number: str = Field(default="+7 705 876 27 95", alias="EXECUTOR_KASPI_NUMBER")
    executor_kaspi_receiver: str = Field(
        default="Кияшев Жанибек Даулетович", alias="EXECUTOR_KASPI_RECEIVER"
    )
    contract_number_start: int = Field(default=1, alias="CONTRACT_NUMBER_START")

    quick_mode_require_phone: bool = Field(default=False, alias="QUICK_MODE_REQUIRE_PHONE")
    release_contract_number_on_delete: bool = Field(
        default=False, alias="RELEASE_CONTRACT_NUMBER_ON_DELETE"
    )

    executor_email: str = Field(default="", alias="EXECUTOR_EMAIL")
    objection_allowed_telegram_ids: str = Field(default="", alias="OBJECTION_ALLOWED_TELEGRAM_IDS")

    @field_validator("storage_path", mode="after")
    @classmethod
    def _resolve_storage_path(cls, value: Path) -> Path:
        return value.resolve()

    @property
    def superadmin_ids(self) -> set[int]:
        return self._parse_ids(self.superadmin_telegram_ids)

    @property
    def objection_allowed_ids(self) -> set[int]:
        """Telegram IDs allowed to use the 'Сформировать возражение' feature. This is a
        separate, narrower allow-list from the general open-access contract flow - by
        explicit request, objection generation stays restricted to specific people."""
        return self._parse_ids(self.objection_allowed_telegram_ids)

    @staticmethod
    def _parse_ids(raw: str) -> set[int]:
        ids: set[int] = set()
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if chunk:
                ids.add(int(chunk))
        return ids

    @property
    def uploads_dir(self) -> Path:
        return self.storage_path / "uploads"

    @property
    def documents_dir(self) -> Path:
        return self.storage_path / "documents"

    @property
    def backups_dir(self) -> Path:
        return self.storage_path / "backups"

    @property
    def objections_dir(self) -> Path:
        return self.storage_path / "objections"

    @property
    def signature_assets_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "templates" / "assets" / "signature"

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "templates" / "contracts"

    @property
    def objection_templates_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "templates" / "objections"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    settings.objections_dir.mkdir(parents=True, exist_ok=True)
    return settings
