from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from importlib import resources
from importlib.metadata import version
from itertools import batched
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import overload
from typing import Protocol
from typing import TYPE_CHECKING
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import urlunparse

import aiohttp
import aiosqlite
from aiopathlib import AsyncPath
from tldm import tldm

from sqlite_export_for_ynab import ddl

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence
    from typing import Never


_EntryTable = (
    Literal["accounts"]
    | Literal["account_periodic_values"]
    | Literal["category_groups"]
    | Literal["categories"]
    | Literal["payees"]
    | Literal["transactions"]
    | Literal["subtransactions"]
    | Literal["scheduled_transactions"]
    | Literal["scheduled_subtransactions"]
)
_Endpoint = (
    Literal["accounts"]
    | Literal["categories"]
    | Literal["payees"]
    | Literal["transactions"]
    | Literal["scheduled_transactions"]
)
_ENDPOINTS = tuple(lit.__args__[0] for lit in _Endpoint.__args__)
_ALL_RELATIONS = frozenset(
    ("plans", "flat_transactions", "scheduled_flat_transactions")
    + tuple(lit.__args__[0] for lit in _EntryTable.__args__)
)

_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"

_PACKAGE = "sqlite-export-for-ynab"

_BATCH_SIZE = 100


def resolve_token(token_override: str | None = None) -> str:
    token = token_override or os.environ.get(_ENV_TOKEN)
    if token:
        return token

    raise ValueError(
        f"Must set YNAB access token as {_ENV_TOKEN!r} environment variable or pass token_override directly. See https://api.ynab.com/#personal-access-tokens"
    )


async def async_main(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    parser = argparse.ArgumentParser(prog=_PACKAGE)
    parser.add_argument(
        "--db",
        help="The path to the SQLite database file.",
        type=Path,
        default=default_db_path(),
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="**DROP ALL TABLES** and fetch all data again.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version(_PACKAGE)}"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all CLI output, including progress bars.",
    )

    args = parser.parse_args(argv)
    db: Path = args.db
    full_refresh: bool = args.full_refresh
    quiet: bool = args.quiet

    token = resolve_token(token_override)

    await sync(token, db, full_refresh, quiet=quiet)

    return 0


def default_db_path() -> Path:
    return (
        (
            Path(xdg_data_home)
            if (xdg_data_home := os.environ.get("XDG_DATA_HOME"))
            else Path.home() / ".local" / "share"
        )
        / _PACKAGE
        / "db.sqlite"
    )


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


async def sync(
    token: str, db: Path, full_refresh: bool, *, quiet: bool = False
) -> None:
    async with aiohttp.ClientSession() as session:
        plans = (await YnabClient(token, session)("plans"))["plans"]

    plan_ids = [plan["id"] for plan in plans]

    await AsyncPath(db).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row

        if full_refresh:
            _print("Dropping relations...", quiet=quiet)
            async with con.cursor() as cur:
                await cur.executescript(await contents("drop-relations.sql"))
            await con.commit()
            _print("Done", quiet=quiet)

        async with con.cursor() as cur:
            relations = await get_relations(cur)
            if relations != _ALL_RELATIONS:
                _print("Recreating relations...", quiet=quiet)
                await cur.executescript(await contents("create-relations.sql"))
                await con.commit()
                _print("Done", quiet=quiet)

        _print("Fetching plan data...", quiet=quiet)
        async with con.cursor() as cur:
            lkos = await get_last_knowledge_of_server(cur)
        async with aiohttp.ClientSession() as session:
            with tldm(
                desc="Plan Data", total=len(plans) * len(_ENDPOINTS), disable=quiet
            ) as pbar:
                yc = ProgressYnabClient(YnabClient(token, session), pbar)

                endpoint_data = dict(
                    zip(
                        _ENDPOINTS,
                        await asyncio.gather(
                            *(
                                asyncio.gather(*jobs(yc, endpoint, plan_ids, lkos))
                                for endpoint in _ENDPOINTS
                            )
                        ),
                        strict=True,
                    )
                )

            all_account_data = endpoint_data["accounts"]
            all_cat_data = endpoint_data["categories"]
            all_payee_data = endpoint_data["payees"]
            all_txn_data = endpoint_data["transactions"]
            all_sched_txn_data = endpoint_data["scheduled_transactions"]

            new_lkos = {
                plan_id: transaction_data["server_knowledge"]
                for plan_id, transaction_data in zip(
                    plan_ids, all_txn_data, strict=True
                )
            }
        _print("Done", quiet=quiet)

        if (
            not any(t["accounts"] for t in all_account_data)
            and not any(t["category_groups"] for t in all_cat_data)
            and not any(p["payees"] for p in all_payee_data)
            and not any(t["transactions"] for t in all_txn_data)
            and not any(s["scheduled_transactions"] for s in all_sched_txn_data)
        ):
            _print("No new data fetched", quiet=quiet)
        else:
            _print("Inserting plan data...", quiet=quiet)
            await insert_plan_data(
                con,
                plans,
                plan_ids,
                all_account_data,
                all_cat_data,
                all_payee_data,
                all_txn_data,
                all_sched_txn_data,
                new_lkos,
                quiet=quiet,
            )
            await con.commit()
            _print("Done", quiet=quiet)


async def contents(filename: str) -> str:
    return await AsyncPath(resources.files(ddl) / filename).read_text()


async def get_relations(cur: aiosqlite.Cursor) -> set[str]:
    await cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' OR type='view'"
    )
    return {t["name"] for t in await cur.fetchall()}


async def get_last_knowledge_of_server(cur: aiosqlite.Cursor) -> dict[str, int]:
    await cur.execute(
        "SELECT id, last_knowledge_of_server FROM plans",
    )
    return {r["id"]: r["last_knowledge_of_server"] for r in await cur.fetchall()}


async def insert_plan_data(
    con: aiosqlite.Connection,
    plans: list[dict[str, Any]],
    plan_ids: list[str],
    all_account_data: list[dict[str, Any]],
    all_cat_data: list[dict[str, Any]],
    all_payee_data: list[dict[str, Any]],
    all_txn_data: list[dict[str, Any]],
    all_sched_txn_data: list[dict[str, Any]],
    new_lkos: dict[str, int],
    *,
    quiet: bool,
) -> None:
    await insert_plans(con, plans, new_lkos)
    await asyncio.gather(
        *(
            insert_accounts(
                con,
                plan_id,
                account_data["accounts"],
                quiet=quiet,
            )
            for plan_id, account_data in zip(plan_ids, all_account_data, strict=True)
        ),
        *(
            insert_category_groups(
                con,
                plan_id,
                cat_data["category_groups"],
                quiet=quiet,
            )
            for plan_id, cat_data in zip(plan_ids, all_cat_data, strict=True)
        ),
        *(
            insert_payees(con, plan_id, payee_data["payees"], quiet=quiet)
            for plan_id, payee_data in zip(plan_ids, all_payee_data, strict=True)
        ),
    )
    await asyncio.gather(
        *(
            insert_transactions(
                con,
                plan_id,
                txn_data["transactions"],
                quiet=quiet,
            )
            for plan_id, txn_data in zip(plan_ids, all_txn_data, strict=True)
        ),
        *(
            insert_scheduled_transactions(
                con,
                plan_id,
                sched_txn_data["scheduled_transactions"],
                quiet=quiet,
            )
            for plan_id, sched_txn_data in zip(
                plan_ids, all_sched_txn_data, strict=True
            )
        ),
    )


async def insert_plans(
    con: aiosqlite.Connection, plans: list[dict[str, Any]], lkos: dict[str, int]
) -> None:
    async with con.cursor() as cur:
        for plan_batch in batched(plans, _BATCH_SIZE):
            await cur.executemany(
                """
                INSERT OR REPLACE INTO plans (
                    id
                    , name
                    , currency_format_currency_symbol
                    , currency_format_decimal_digits
                    , currency_format_decimal_separator
                    , currency_format_display_symbol
                    , currency_format_group_separator
                    , currency_format_iso_code
                    , currency_format_symbol_first
                    , last_knowledge_of_server
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        plan_id := plan["id"],
                        plan["name"],
                        plan["currency_format"]["currency_symbol"],
                        plan["currency_format"]["decimal_digits"],
                        plan["currency_format"]["decimal_separator"],
                        plan["currency_format"]["display_symbol"],
                        plan["currency_format"]["group_separator"],
                        plan["currency_format"]["iso_code"],
                        plan["currency_format"]["symbol_first"],
                        lkos[plan_id],
                    )
                    for plan in plan_batch
                ),
            )


_LOAN_ACCOUNT_PERIODIC_VALUES = frozenset(
    ("debt_escrow_amounts", "debt_interest_rates", "debt_minimum_payments")
)


async def insert_accounts(
    con: aiosqlite.Connection,
    plan_id: str,
    accounts: list[dict[str, Any]],
    *,
    quiet: bool = False,
) -> None:
    # YNAB's LoanAccountPeriodValues are untyped dicts so we need to turn them into a more standard sub-entry view
    updated_accounts = [
        {
            "account_periodic_values": [
                {
                    "name": key,
                    "account_id": account["id"],
                    "date": apvk,
                    "amount": apvv,
                }
                for key in _LOAN_ACCOUNT_PERIODIC_VALUES
                for apvk, apvv in account[key].items()
            ]
        }
        | {k: v for k, v in account.items() if k not in _LOAN_ACCOUNT_PERIODIC_VALUES}
        for account in accounts
    ]

    await insert_nested_entries(
        con,
        plan_id,
        updated_accounts,
        "Accounts",
        "accounts",
        "account_periodic_values",
        "account_periodic_values",
        quiet=quiet,
    )


async def insert_category_groups(
    con: aiosqlite.Connection,
    plan_id: str,
    category_groups: list[dict[str, Any]],
    *,
    quiet: bool = False,
) -> None:
    await insert_nested_entries(
        con,
        plan_id,
        category_groups,
        "Categories",
        "category_groups",
        "categories",
        "categories",
        quiet=quiet,
    )


async def insert_payees(
    con: aiosqlite.Connection,
    plan_id: str,
    payees: list[dict[str, Any]],
    *,
    quiet: bool = False,
) -> None:
    if not payees:
        return

    with tldm(total=len(payees), desc="Payees", disable=quiet) as pbar:
        await insert_entries(con, "payees", plan_id, payees, pbar)


async def insert_transactions(
    con: aiosqlite.Connection,
    plan_id: str,
    transactions: list[dict[str, Any]],
    *,
    quiet: bool = False,
) -> None:
    await insert_nested_entries(
        con,
        plan_id,
        transactions,
        "Transactions",
        "transactions",
        "subtransactions",
        "subtransactions",
        quiet=quiet,
    )


async def insert_scheduled_transactions(
    con: aiosqlite.Connection,
    plan_id: str,
    scheduled_transactions: list[dict[str, Any]],
    *,
    quiet: bool = False,
) -> None:
    await insert_nested_entries(
        con,
        plan_id,
        scheduled_transactions,
        "Scheduled Transactions",
        "scheduled_transactions",
        "subtransactions",
        "scheduled_subtransactions",
        quiet=quiet,
    )


@overload
async def insert_nested_entries(
    con: aiosqlite.Connection,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Accounts"],
    entries_name: Literal["accounts"],
    subentries_name: Literal["account_periodic_values"],
    subentries_table_name: Literal["account_periodic_values"],
    *,
    quiet: bool = False,
) -> None: ...


@overload
async def insert_nested_entries(
    con: aiosqlite.Connection,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Categories"],
    entries_name: Literal["category_groups"],
    subentries_name: Literal["categories"],
    subentries_table_name: Literal["categories"],
    *,
    quiet: bool = False,
) -> None: ...


@overload
async def insert_nested_entries(
    con: aiosqlite.Connection,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Transactions"],
    entries_name: Literal["transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["subtransactions"],
    *,
    quiet: bool = False,
) -> None: ...


@overload
async def insert_nested_entries(
    con: aiosqlite.Connection,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Scheduled Transactions"],
    entries_name: Literal["scheduled_transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["scheduled_subtransactions"],
    *,
    quiet: bool = False,
) -> None: ...


async def insert_nested_entries(
    con: aiosqlite.Connection,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: (
        Literal["Accounts"]
        | Literal["Categories"]
        | Literal["Transactions"]
        | Literal["Scheduled Transactions"]
    ),
    entries_name: (
        Literal["accounts"]
        | Literal["category_groups"]
        | Literal["transactions"]
        | Literal["scheduled_transactions"]
    ),
    subentries_name: (
        Literal["account_periodic_values"]
        | Literal["categories"]
        | Literal["subtransactions"]
    ),
    subentries_table_name: (
        Literal["account_periodic_values"]
        | Literal["categories"]
        | Literal["subtransactions"]
        | Literal["scheduled_subtransactions"]
    ),
    *,
    quiet: bool = False,
) -> None:
    if not entries:
        return

    with tldm(
        total=sum(1 + len(e[subentries_name]) for e in entries),
        desc=desc,
        disable=quiet,
    ) as pbar:
        await insert_entries(
            con,
            entries_name,
            plan_id,
            [
                {k: v for k, v in entry.items() if k != subentries_name}
                for entry in entries
            ],
            pbar,
        )
        await insert_entries(
            con,
            subentries_table_name,
            plan_id,
            [subentry for entry in entries for subentry in entry[subentries_name]],
            pbar,
        )


async def insert_entries(
    con: aiosqlite.Connection,
    table: _EntryTable,
    plan_id: str,
    entries: list[dict[str, Any]],
    pbar: tldm[Never],
) -> None:
    if not entries:
        return

    entry_keys = tuple(entries[0])
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(entry_keys + ('plan_id',))}) VALUES ({', '.join('?' * (len(entry_keys) + 1))})"

    async with con.cursor() as cur:
        for entry_batch in batched(entries, _BATCH_SIZE):
            values_batch = [
                tuple(entry[key] for key in entry_keys) + (plan_id,)
                for entry in entry_batch
            ]
            await cur.executemany(sql, values_batch)
            pbar.update(len(values_batch))


def jobs(
    yc: SupportsYnabClient,
    endpoint: _Endpoint,
    plan_ids: list[str],
    lkos: dict[str, int],
) -> list[Awaitable[dict[str, Any]]]:
    return [
        yc(f"plans/{plan_id}/{endpoint}", last_knowledge_of_server=lkos.get(plan_id))
        for plan_id in plan_ids
    ]


class SupportsYnabClient(Protocol):
    async def __call__(
        self, path: str, last_knowledge_of_server: int | None = None
    ) -> dict[str, Any]: ...


@dataclass
class ProgressYnabClient:
    yc: YnabClient
    pbar: tldm[Never]

    async def __call__(
        self, path: str, last_knowledge_of_server: int | None = None
    ) -> dict[str, Any]:
        try:
            return await self.yc(path, last_knowledge_of_server)
        finally:
            self.pbar.update()


@dataclass
class YnabClient:
    BASE_SCHEME: ClassVar[str] = "https"
    BASE_NETLOC: ClassVar[str] = "api.ynab.com"
    BASE_PATH: ClassVar[str] = "v1/"

    token: str
    session: aiohttp.ClientSession

    async def __call__(
        self, path: str, last_knowledge_of_server: int | None = None
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        url = urlunparse(
            (
                self.BASE_SCHEME,
                self.BASE_NETLOC,
                urljoin(self.BASE_PATH, path),
                "",
                urlencode(
                    {"last_knowledge_of_server": last_knowledge_of_server}
                    if last_knowledge_of_server
                    else {}
                ),
                "",
            )
        )

        for i in range(3):
            try:
                async with self.session.get(url, headers=headers) as resp:
                    body = await resp.text()

                return json.loads(body)["data"]
            except Exception:
                if i == 2:
                    raise

        raise AssertionError("unreachable")


def main(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    return asyncio.run(async_main(argv, token_override=token_override))
