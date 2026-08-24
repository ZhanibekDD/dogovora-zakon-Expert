from __future__ import annotations

from pydantic import BaseModel


class ContractRenderContext(BaseModel):
    """Everything docxtpl needs to fill the master template for one contract."""

    contract_number: int
    contract_date: str
    contract_city: str

    client_full_name: str
    client_iin: str
    client_phone: str
    client_address: str

    service_subject: str
    service_actions: str
    result_definition: str

    amount_digits: str
    amount_words: str
    payment_terms: str
    work_period: str
    penalty_clause: str

    executor_name: str
    executor_full_name: str
    executor_brand_name: str
    executor_identifier_label: str
    executor_identifier: str
    executor_director_name: str
    executor_signer_short_name: str
    executor_phone: str
    executor_address: str
    executor_website: str
    executor_payment_details: str

    executor_bank_beneficiary: str
    executor_bank_beneficiary_identifier: str
    executor_bank_name: str
    executor_bank_bic: str
    executor_bank_iban: str
    executor_bank_payment_purpose: str
    executor_kaspi_number: str
    executor_kaspi_receiver: str

    executor_signature: str | None = None
    executor_stamp: str | None = None
    client_signature: str | None = None
    client_signature_date: str | None = None
