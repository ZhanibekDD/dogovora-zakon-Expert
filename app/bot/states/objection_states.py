from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ObjectionStates(StatesGroup):
    """States for the 'Сформировать возражение' flow: one writ photo/PDF + caption in, a
    finished objection DOCX+PDF out, with at most one short clarification round-trip."""

    waiting_for_document = State()
    waiting_for_clarification = State()
