from __future__ import annotations

import base64
import datetime
import io
from pathlib import Path

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import CLIENT_CONSENT_TEXT, ContractStatus
from app.core.security import generate_token, hash_token, sha256_file, verify_token
from app.database.models.contract import Contract
from app.database.models.signature import ClientSignature, SigningToken
from app.services import pdf_service
from app.services.contract_service import now_almaty
from app.services.storage_service import contract_dir

SIGNING_FEEDBACK_REASONS: dict[str, str] = {
    "price": "Стоимость выше ожиданий",
    "result": "Неясно, какой результат я получу",
    "deadline": "Не устраивает или непонятен срок",
    "payment_requisites": "Есть сомнения по реквизитам оплаты",
    "need_time": "Нужно время на решение",
    "other": "Другая причина",
}


class SigningError(Exception):
    pass


class TokenExpiredError(SigningError):
    pass


class TokenAlreadyUsedError(SigningError):
    pass


class TokenInvalidError(SigningError):
    pass


class BlankSignatureError(SigningError):
    pass


def get_consent_text() -> str:
    return CLIENT_CONSENT_TEXT


def normalize_feedback_reason(reason: str) -> tuple[str, str]:
    code = (reason or "").strip().lower()
    label = SIGNING_FEEDBACK_REASONS.get(code)
    if label is None:
        raise SigningError("Неизвестная причина")
    return code, label


async def create_signing_token(session: AsyncSession, contract: Contract, created_by_id: int) -> str:
    """Create a one-time signing link token. Only the SHA-256 hash is stored."""
    settings = get_settings()
    raw_token, token_hash = generate_token()
    expires_at = now_almaty() + datetime.timedelta(hours=settings.signing_token_ttl_hours)

    session.add(
        SigningToken(
            contract_id=contract.id,
            token_hash=token_hash,
            expires_at=expires_at.replace(tzinfo=None),
            created_by_id=created_by_id,
        )
    )
    contract.status = ContractStatus.SENT_FOR_SIGNATURE.value
    await session.flush()
    return raw_token


def build_signing_url(contract_id: int, raw_token: str) -> str:
    settings = get_settings()
    return f"{settings.app_base_url}/sign/{contract_id}?token={raw_token}"


async def resolve_signing_token(
    session: AsyncSession, contract_id: int, raw_token: str
) -> SigningToken:
    from sqlalchemy import select

    token_hash = hash_token(raw_token)
    result = await session.execute(
        select(SigningToken).where(
            SigningToken.contract_id == contract_id,
            SigningToken.token_hash == token_hash,
        )
    )
    token = result.scalar_one_or_none()
    if token is None or not verify_token(raw_token, token.token_hash):
        raise TokenInvalidError("Недействительная ссылка для подписания")
    if token.revoked_at is not None:
        raise TokenInvalidError("Ссылка для подписания отозвана")
    if token.used_at is not None:
        raise TokenAlreadyUsedError("Эта ссылка уже была использована для подписания")
    now_naive = now_almaty().replace(tzinfo=None)
    if token.expires_at < now_naive:
        raise TokenExpiredError("Срок действия ссылки истёк")
    return token


def _decode_signature_png(data_url: str) -> bytes:
    if "," in data_url:
        _, encoded = data_url.split(",", 1)
    else:
        encoded = data_url
    raw = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(raw))
    image.load()
    extrema = image.convert("L").getextrema()
    if extrema[0] == extrema[1] == 255 or extrema == (0, 0):
        raise BlankSignatureError("Подпись не может быть пустой")
    bbox = image.convert("L").point(lambda p: 255 if p < 250 else 0).getbbox()
    if bbox is None:
        raise BlankSignatureError("Подпись не может быть пустой")
    return raw


async def complete_signing(
    session: AsyncSession,
    *,
    contract: Contract,
    token: SigningToken,
    signature_data_url: str,
    consent_accepted: bool,
    client_telegram_id: int | None,
    ip_address: str | None,
    user_agent: str | None,
) -> ClientSignature:
    """Finalize the client's simple electronic signature act."""
    if not consent_accepted:
        raise SigningError("Требуется согласие с условиями договора")
    if token.used_at is not None:
        raise TokenAlreadyUsedError("Эта ссылка уже была использована для подписания")

    signature_png = _decode_signature_png(signature_data_url)

    original_pdf_path = contract.pdf_path
    if not original_pdf_path:
        raise SigningError("У договора отсутствует утверждённый PDF-файл")
    original_sha256 = sha256_file(original_pdf_path)

    directory = contract_dir(contract.id)
    signature_image_path = directory / f"client_signature_{contract.id}_{contract.version}.png"
    signature_image_path.write_bytes(signature_png)

    signed_at = now_almaty()
    signed_pdf_path = directory / f"signed_v{contract.version}.pdf"
    pdf_service.overlay_client_signature(
        input_pdf_path=Path(original_pdf_path),
        output_pdf_path=signed_pdf_path,
        signature_png_bytes=signature_png,
        signed_at_text=signed_at.strftime("%d.%m.%Y %H:%M %Z"),
    )
    signed_sha256 = sha256_file(str(signed_pdf_path))

    client_signature = ClientSignature(
        contract_id=contract.id,
        client_id=contract.client_id,
        signature_image_path=str(signature_image_path),
        consent_text=CLIENT_CONSENT_TEXT,
        ip_address=ip_address,
        user_agent=user_agent,
        telegram_id=client_telegram_id,
        original_pdf_sha256=original_sha256,
        signed_pdf_sha256=signed_sha256,
        contract_version=contract.version,
        signed_at=signed_at.replace(tzinfo=None),
    )
    session.add(client_signature)

    token.used_at = signed_at.replace(tzinfo=None)
    contract.pdf_path = str(signed_pdf_path)
    contract.document_sha256 = signed_sha256
    contract.status = ContractStatus.SIGNED.value
    contract.signed_at = signed_at.replace(tzinfo=None)

    await session.flush()
    return client_signature


async def revoke_signing_token(session: AsyncSession, token: SigningToken) -> None:
    token.revoked_at = now_almaty().replace(tzinfo=None)
    await session.flush()
