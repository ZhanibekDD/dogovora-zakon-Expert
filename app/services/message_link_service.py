from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_MESSAGE_LINK_TTL_SECONDS = 60 * 24 * 3600  # 60 days: long enough to edit an old draft by reply
_PENDING_CLARIFICATION_TTL_SECONDS = 30 * 60  # 30 minutes: don't keep stale drafts forever

_redis_client_override: aioredis.Redis | None = None


def set_redis_client_for_testing(client: aioredis.Redis | None) -> None:
    """Test-only hook: inject a fakeredis client instead of connecting to a real server."""
    global _redis_client_override
    _redis_client_override = client


def _client() -> aioredis.Redis:
    if _redis_client_override is not None:
        return _redis_client_override
    return aioredis.from_url(get_settings().redis_url)


def _message_key(chat_id: int, message_id: int) -> str:
    return f"zakonexpert:msg_contract:{chat_id}:{message_id}"


def _pending_key(chat_id: int, namespace: str) -> str:
    return f"zakonexpert:pending_{namespace}:{chat_id}"


async def link_message_to_contract(chat_id: int, message_id: int, contract_id: int) -> None:
    """Remember that this Telegram message displays `contract_id`, so a later reply to it
    (a natural-language edit instruction) can be resolved back to the right contract."""
    client = _client()
    await client.set(_message_key(chat_id, message_id), contract_id, ex=_MESSAGE_LINK_TTL_SECONDS)


async def resolve_contract_id(chat_id: int, message_id: int) -> int | None:
    client = _client()
    value = await client.get(_message_key(chat_id, message_id))
    if value is None:
        return None
    return int(value)


async def save_pending_clarification(
    chat_id: int, payload: dict[str, Any], *, namespace: str = "quick"
) -> None:
    """Cache partially-extracted data while we wait for the employee's one-line answer to a
    missing-field clarification question. `namespace` keeps independent flows (quick-mode
    contracts vs. objections) from colliding if both happen to be pending in the same chat."""
    client = _client()
    await client.set(
        _pending_key(chat_id, namespace), json.dumps(payload), ex=_PENDING_CLARIFICATION_TTL_SECONDS
    )


async def load_pending_clarification(chat_id: int, *, namespace: str = "quick") -> dict[str, Any] | None:
    client = _client()
    raw = await client.get(_pending_key(chat_id, namespace))
    if raw is None:
        return None
    return json.loads(raw)


async def clear_pending_clarification(chat_id: int, *, namespace: str = "quick") -> None:
    client = _client()
    await client.delete(_pending_key(chat_id, namespace))
