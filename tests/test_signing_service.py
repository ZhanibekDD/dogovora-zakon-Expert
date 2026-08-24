from __future__ import annotations

import base64
import datetime
import io
from pathlib import Path

import pytest
from PIL import Image
from reportlab.pdfgen import canvas
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.client import Client
from app.database.models.contract import Contract
from app.services import signing_service


def _blank_png_data_url() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 150), (255, 255, 255)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _drawn_png_data_url() -> str:
    image = Image.new("RGB", (300, 150), (255, 255, 255))
    for x in range(50, 250):
        image.putpixel((x, 75), (0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


async def _make_approved_contract(session: AsyncSession, tmp_path: Path) -> Contract:
    client = Client(full_name="Тестовый Клиент", iin="010312500019")
    session.add(client)
    await session.flush()

    pdf_path = tmp_path / "approved.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=(595, 842))
    c.drawString(72, 800, "Approved contract text")
    c.save()

    from app.database.models.user import User
    from app.database.repositories.user_repo import get_role_by_code

    role = await get_role_by_code(session, "admin")
    manager = User(telegram_id=555, full_name="Admin", role_id=role.id)
    session.add(manager)
    await session.flush()

    contract = Contract(
        contract_number=1,
        status="approved",
        client_id=client.id,
        manager_id=manager.id,
        amount=10000,
        service_data={},
        result_data={},
        pdf_path=str(pdf_path),
        version=1,
    )
    session.add(contract)
    await session.flush()
    return contract


async def test_signing_token_is_valid_and_hash_only_stored(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)

    assert raw_token
    from sqlalchemy import select

    from app.database.models.signature import SigningToken

    result = await db_session.execute(select(SigningToken).where(SigningToken.contract_id == contract.id))
    stored = result.scalar_one()
    assert stored.token_hash != raw_token

    token = await signing_service.resolve_signing_token(db_session, contract.id, raw_token)
    assert token.id == stored.id


async def test_expired_token_rejected(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)

    from sqlalchemy import select

    from app.database.models.signature import SigningToken

    result = await db_session.execute(select(SigningToken).where(SigningToken.contract_id == contract.id))
    stored = result.scalar_one()
    stored.expires_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    await db_session.flush()

    with pytest.raises(signing_service.TokenExpiredError):
        await signing_service.resolve_signing_token(db_session, contract.id, raw_token)


async def test_token_cannot_be_reused_after_signing(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)
    token = await signing_service.resolve_signing_token(db_session, contract.id, raw_token)

    await signing_service.complete_signing(
        db_session,
        contract=contract,
        token=token,
        signature_data_url=_drawn_png_data_url(),
        consent_accepted=True,
        client_telegram_id=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    with pytest.raises(signing_service.TokenAlreadyUsedError):
        await signing_service.resolve_signing_token(db_session, contract.id, raw_token)


async def test_blank_signature_canvas_rejected(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)
    token = await signing_service.resolve_signing_token(db_session, contract.id, raw_token)

    with pytest.raises(signing_service.BlankSignatureError):
        await signing_service.complete_signing(
            db_session,
            contract=contract,
            token=token,
            signature_data_url=_blank_png_data_url(),
            consent_accepted=True,
            client_telegram_id=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )


async def test_signing_requires_explicit_consent(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)
    token = await signing_service.resolve_signing_token(db_session, contract.id, raw_token)

    with pytest.raises(signing_service.SigningError):
        await signing_service.complete_signing(
            db_session,
            contract=contract,
            token=token,
            signature_data_url=_drawn_png_data_url(),
            consent_accepted=False,
            client_telegram_id=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )


async def test_document_hash_recorded_after_signing(db_session: AsyncSession, tmp_path: Path) -> None:
    contract = await _make_approved_contract(db_session, tmp_path)
    raw_token = await signing_service.create_signing_token(db_session, contract, created_by_id=1)
    token = await signing_service.resolve_signing_token(db_session, contract.id, raw_token)

    client_signature = await signing_service.complete_signing(
        db_session,
        contract=contract,
        token=token,
        signature_data_url=_drawn_png_data_url(),
        consent_accepted=True,
        client_telegram_id=42,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
    )

    assert client_signature.original_pdf_sha256
    assert client_signature.signed_pdf_sha256
    assert client_signature.original_pdf_sha256 != client_signature.signed_pdf_sha256
    assert contract.status == "signed"
    assert contract.document_sha256 == client_signature.signed_pdf_sha256
    assert contract.signed_at.tzinfo is None
    assert client_signature.signed_at.tzinfo is None


def test_feedback_reasons_are_whitelisted() -> None:
    code, label = signing_service.normalize_feedback_reason("payment_requisites")
    assert code == "payment_requisites"
    assert "реквизит" in label.lower()
    with pytest.raises(signing_service.SigningError):
        signing_service.normalize_feedback_reason("arbitrary-free-text")
