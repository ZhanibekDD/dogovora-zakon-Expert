from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class QuickContractStates(StatesGroup):
    """States for the default 'quick' contract flow: one document+caption message in, a
    finished draft out, with at most one short clarification round-trip in between."""

    waiting_for_document = State()
    waiting_for_clarification = State()
    waiting_for_redo_conditions = State()


class SignatureUploadStates(StatesGroup):
    waiting_for_signature_png = State()
    waiting_for_stamp_png = State()


class EmployeeManagementStates(StatesGroup):
    waiting_for_new_employee_id = State()
    waiting_for_new_employee_role = State()
    waiting_for_block_employee_id = State()


class SettingsStates(StatesGroup):
    waiting_for_next_contract_number = State()
    waiting_for_next_contract_number_reason = State()


class FindContractStates(StatesGroup):
    waiting_for_query = State()
