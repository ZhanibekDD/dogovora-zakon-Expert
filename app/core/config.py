from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
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
        default="Товарищество с ограниченной ответственностью «ZakonExpert»",
        alias="EXECUTOR_FULL_NAME",
    )
    executor_brand_name: str = Field(default="ТОО «ZakonExpert»", alias="EXECUTOR_BRAND_NAME")
    executor_display_name: str = Field(default="ТОО «ZakonExpert»", alias="EXECUTOR_DISPLAY_NAME")
    executor_identifier_label: str = Field(default="БИН", alias="EXECUTOR_IDENTIFIER_LABEL")
    executor_identifier: str = Field(
        default="260740044168",
        validation_alias=AliasChoices("EXECUTOR_IDENTIFIER", "EXECUTOR_BIN", "EXECUTOR_IIN"),
    )
    executor_director_name: str = Field(
        default="Кияшев Жанибек Даулетович",
        alias="EXECUTOR_DIRECTOR_NAME",
    )
    executor_signer_short_name: str = Field(
        default="Кияшев Ж.Д.",
        alias="EXECUTOR_SIGNER_SHORT_NAME",
    )
    executor_address: str = Field(
        default="Республика Казахстан, область Жетісу, г. Талдыкорган, ул. Акын Сара, 152",
        alias="EXECUTOR_ADDRESS",
    )
    executor_phone: str = Field(default="+7 705 876 27 95", alias="EXECUTOR_PHONE")
    executor_website: str = Field(default="zakonexpertt.kz", alias="EXECUTOR_WEBSITE")

    # The bank beneficiary is deliberately stored separately from the legal executor.
    # This prevents the contract from falsely presenting a personal/IE account as a TOO account.
    executor_bank_beneficiary: str = Field(
        default="Жанибек Кияшев Даулетович", alias="EXECUTOR_BANK_BENEFICIARY"
    )
    executor_bank_beneficiary_identifier: str = Field(
        default="000725500183", alias="EXECUTOR_BANK_BENEFICIARY_IDENTIFIER"
    )
    executor_bank_name: str = Field(
        default="АО «Фридом Банк Казахстан»", alias="EXECUTOR_BANK_NAME"
    )
    executor_bank_bic: str = Field(default="KSNVKZKA", alias="EXECUTOR_BANK_BIC")
    executor_bank_iban: str = Field(
        default="KZ95551V600001202152", alias="EXECUTOR_BANK_IBAN"
    )
    executor_bank_payment_purpose: str = Field(
        default="Оплата по договору оказания услуг", alias="EXECUTOR_BANK_PAYMENT_PURPOSE"
    )

    executor_kaspi_number: str = Field(default="+7 705 876 27 95", alias="EXECUTOR_KASPI_NUMBER")
    executor_kaspi_receiver: str = Field(
        default="Кияшев Жанибек Даулетович", alias="EXECUTOR_KASPI_RECEIVER"
    )
    executor_payment_details: str = Field(
        default=(
            "по банковским реквизитам и/или Kaspi, указанным в разделе 9 настоящего договора"
        ),
        alias="EXECUTOR_PAYMENT_DETAILS",
    )

    executor_signature_width_mm: float = Field(
        default=47.0,
        alias="EXECUTOR_SIGNATURE_WIDTH_MM",
        ge=30,
        le=60,
    )
    executor_stamp_diameter_mm: float = Field(
        default=31.5,
        alias="EXECUTOR_STAMP_DIAMETER_MM",
        ge=28,
        le=38,
    )
    executor_signature_block_width_mm: float = Field(
        default=80.0,
        alias="EXECUTOR_SIGNATURE_BLOCK_WIDTH_MM",
        ge=74,
        le=84,
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
        """Telegram IDs allowed to use the 'Сформировать возражение' feature."""
        return self._parse_ids(self.objection_allowed_telegram_ids)

    @property
    def executor_iin(self) -> str:
        """Backward-compatible alias for deployments still referencing the old IP field."""
        return self.executor_identifier

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
