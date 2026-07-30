from __future__ import annotations

import fakeredis.aioredis
import pytest

from app.services import message_link_service


@pytest.fixture(autouse=True)
def _fake_redis():
    client = fakeredis.aioredis.FakeRedis()
    message_link_service.set_redis_client_for_testing(client)
    yield client
    message_link_service.set_redis_client_for_testing(None)


async def test_link_and_resolve_message_to_contract() -> None:
    await message_link_service.link_message_to_contract(chat_id=1, message_id=100, contract_id=7)
    resolved = await message_link_service.resolve_contract_id(chat_id=1, message_id=100)
    assert resolved == 7


async def test_resolve_unknown_message_returns_none() -> None:
    resolved = await message_link_service.resolve_contract_id(chat_id=1, message_id=999)
    assert resolved is None


async def test_pending_clarification_round_trip() -> None:
    payload = {"identity": {"full_name": "Иванов Иван"}, "conditions": {}, "manager_id": 5}
    await message_link_service.save_pending_clarification(chat_id=42, payload=payload)
    loaded = await message_link_service.load_pending_clarification(chat_id=42)
    assert loaded == payload


async def test_clear_pending_clarification() -> None:
    await message_link_service.save_pending_clarification(chat_id=42, payload={"a": 1})
    await message_link_service.clear_pending_clarification(chat_id=42)
    assert await message_link_service.load_pending_clarification(chat_id=42) is None
