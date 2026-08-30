from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.database.models.contract import Contract
from app.database.session import session_scope
from app.services.crm_sync_service import sync_contract_to_crm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send existing ZakonExpert contracts to CRM in contract-id order."
    )
    parser.add_argument("--from-id", type=int, default=0, help="Start from this contract id")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of contracts; 0 = all")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be synced")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.crm_sync_url.strip() or len(settings.crm_integration_key.strip()) < 24:
        raise SystemExit("CRM_SYNC_URL / CRM_INTEGRATION_KEY are not configured")

    async with session_scope() as session:
        query = select(Contract).where(Contract.id >= max(0, args.from_id)).order_by(Contract.id.asc())
        if args.limit > 0:
            query = query.limit(args.limit)
        result = await session.execute(query)
        contracts = list(result.scalars().unique())

        if args.dry_run:
            for contract in contracts:
                print(
                    f"id={contract.id} number={contract.contract_number} "
                    f"status={contract.status} client={contract.client.full_name}"
                )
            print(f"DRY RUN: {len(contracts)} contract(s)")
            return 0

        ok = 0
        failed = 0
        for index, contract in enumerate(contracts, start=1):
            sent = await sync_contract_to_crm(contract, contract.client)
            if sent:
                ok += 1
                marker = "OK"
            else:
                failed += 1
                marker = "FAIL"
            print(
                f"[{index}/{len(contracts)}] {marker} "
                f"contract #{contract.contract_number} id={contract.id} "
                f"client={contract.client.full_name}"
            )
            # Keep the one-time backfill gentle on shared hosting and the CRM endpoint.
            await asyncio.sleep(0.05)

    print(f"DONE: synced={ok} failed={failed} total={ok + failed}")
    return 0 if failed == 0 else 2


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
