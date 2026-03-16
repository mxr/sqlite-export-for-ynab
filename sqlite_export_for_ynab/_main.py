from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from importlib import resources
from importlib.metadata import version
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
_ALL_RELATIONS = frozenset(
    ("plans", "flat_transactions", "scheduled_flat_transactions")
    + tuple(lit.__args__[0] for lit in _EntryTable.__args__)
)

_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"

_PACKAGE = "sqlite-export-for-ynab"


async def async_main(argv: Sequence[str] | None = None) -> int:
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

    args = parser.parse_args(argv)
    db: Path = args.db
    full_refresh: bool = args.full_refresh

    token = os.environ.get(_ENV_TOKEN)
    if not token:
        raise ValueError(
            f"Must set YNAB access token as {_ENV_TOKEN!r} "
            "environment variable. See "
            "https://api.ynab.com/#personal-access-tokens"
        )

    await sync(token, db, full_refresh)

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


async def sync(token: str, db: Path, full_refresh: bool) -> None:
    async with aiohttp.ClientSession() as session:
        plans = (await YnabClient(token, session)("plans"))["plans"]

    plan_ids = [plan["id"] for plan in plans]

    if not db.exists():
        db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as con:
        con.row_factory = _row_factory
        cur = con.cursor()

        if full_refresh:
            print("Dropping relations...")
            cur.executescript(contents("drop-relations.sql"))
            con.commit()
            print("Done")

        relations = get_relations(cur)
        if relations != _ALL_RELATIONS:
            print("Recreating relations...")
            cur.executescript(contents("create-relations.sql"))
            con.commit()
            print("Done")

        print("Fetching plan data...")
        lkos = get_last_knowledge_of_server(cur)
        async with aiohttp.ClientSession() as session:
            with tldm(desc="Plan Data", total=len(plans) * 5) as pbar:
                yc = ProgressYnabClient(YnabClient(token, session), pbar)

                account_jobs = jobs(yc, "accounts", plan_ids, lkos)
                cat_jobs = jobs(yc, "categories", plan_ids, lkos)
                payee_jobs = jobs(yc, "payees", plan_ids, lkos)
                txn_jobs = jobs(yc, "transactions", plan_ids, lkos)
                sched_txn_jobs = jobs(yc, "scheduled_transactions", plan_ids, lkos)

                data = await asyncio.gather(
                    *account_jobs, *cat_jobs, *payee_jobs, *txn_jobs, *sched_txn_jobs
                )

            la = len(account_jobs)
            lc = len(cat_jobs)
            lp = len(payee_jobs)
            lt = len(txn_jobs)

            all_account_data = data[:la]
            all_cat_data = data[la : la + lc]
            all_payee_data = data[la + lc : la + lc + lp]
            all_txn_data = data[la + lc + lp : la + lc + lp + lt]
            all_sched_txn_data = data[la + lc + lp + lt :]

            new_lkos = {
                plan_id: transaction_data["server_knowledge"]
                for plan_id, transaction_data in zip(
                    plan_ids, all_txn_data, strict=True
                )
            }
        print("Done")

        if (
            not any(t["accounts"] for t in all_account_data)
            and not any(t["category_groups"] for t in all_cat_data)
            and not any(p["payees"] for p in all_payee_data)
            and not any(t["transactions"] for t in all_txn_data)
            and not any(s["scheduled_transactions"] for s in all_sched_txn_data)
        ):
            print("No new data fetched")
        else:
            print("Inserting plan data...")
            insert_plans(cur, plans, new_lkos)
            for plan_id, account_data in zip(plan_ids, all_account_data, strict=True):
                insert_accounts(cur, plan_id, account_data["accounts"])
            for plan_id, cat_data in zip(plan_ids, all_cat_data, strict=True):
                insert_category_groups(cur, plan_id, cat_data["category_groups"])
            for plan_id, payee_data in zip(plan_ids, all_payee_data, strict=True):
                insert_payees(cur, plan_id, payee_data["payees"])
            for plan_id, txn_data in zip(plan_ids, all_txn_data, strict=True):
                insert_transactions(cur, plan_id, txn_data["transactions"])
            for plan_id, sched_txn_data in zip(
                plan_ids, all_sched_txn_data, strict=True
            ):
                insert_scheduled_transactions(
                    cur, plan_id, sched_txn_data["scheduled_transactions"]
                )
            print("Done")


def _row_factory(c: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {d[0]: r for d, r in zip(c.description, row, strict=True)}


def contents(filename: str) -> str:
    return (resources.files(ddl) / filename).read_text()


def get_relations(cur: sqlite3.Cursor) -> set[str]:
    return {
        t["name"]
        for t in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' OR type='view'"
        ).fetchall()
    }


def get_last_knowledge_of_server(cur: sqlite3.Cursor) -> dict[str, int]:
    return {
        r["id"]: r["last_knowledge_of_server"]
        for r in cur.execute(
            "SELECT id, last_knowledge_of_server FROM plans",
        ).fetchall()
    }


def insert_plans(
    cur: sqlite3.Cursor, plans: list[dict[str, Any]], lkos: dict[str, int]
) -> None:
    cur.executemany(
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
            for plan in plans
        ),
    )


_LOAN_ACCOUNT_PERIODIC_VALUES = frozenset(
    ("debt_escrow_amounts", "debt_interest_rates", "debt_minimum_payments")
)


def insert_accounts(
    cur: sqlite3.Cursor, plan_id: str, accounts: list[dict[str, Any]]
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

    return insert_nested_entries(
        cur,
        plan_id,
        updated_accounts,
        "Accounts",
        "accounts",
        "account_periodic_values",
        "account_periodic_values",
    )


def insert_category_groups(
    cur: sqlite3.Cursor, plan_id: str, category_groups: list[dict[str, Any]]
) -> None:
    return insert_nested_entries(
        cur,
        plan_id,
        category_groups,
        "Categories",
        "category_groups",
        "categories",
        "categories",
    )


def insert_payees(
    cur: sqlite3.Cursor, plan_id: str, payees: list[dict[str, Any]]
) -> None:
    if not payees:
        return

    for payee in tldm(payees, desc="Payees"):
        insert_entry(cur, "payees", plan_id, payee)


def insert_transactions(
    cur: sqlite3.Cursor, plan_id: str, transactions: list[dict[str, Any]]
) -> None:
    return insert_nested_entries(
        cur,
        plan_id,
        transactions,
        "Transactions",
        "transactions",
        "subtransactions",
        "subtransactions",
    )


def insert_scheduled_transactions(
    cur: sqlite3.Cursor, plan_id: str, scheduled_transactions: list[dict[str, Any]]
) -> None:
    return insert_nested_entries(
        cur,
        plan_id,
        scheduled_transactions,
        "Scheduled Transactions",
        "scheduled_transactions",
        "subtransactions",
        "scheduled_subtransactions",
    )


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Accounts"],
    entries_name: Literal["accounts"],
    subentries_name: Literal["account_periodic_values"],
    subentries_table_name: Literal["account_periodic_values"],
) -> None: ...


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Categories"],
    entries_name: Literal["category_groups"],
    subentries_name: Literal["categories"],
    subentries_table_name: Literal["categories"],
) -> None: ...


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Transactions"],
    entries_name: Literal["transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["subtransactions"],
) -> None: ...


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Scheduled Transactions"],
    entries_name: Literal["scheduled_transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["scheduled_subtransactions"],
) -> None: ...


def insert_nested_entries(
    cur: sqlite3.Cursor,
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
) -> None:
    if not entries:
        return

    with tldm(
        total=sum(1 + len(e[subentries_name]) for e in entries),
        desc=desc,
    ) as pbar:
        for entry in entries:
            insert_entry(
                cur,
                entries_name,
                plan_id,
                {k: v for k, v in entry.items() if k != subentries_name},
            )
            pbar.update()

            for subentry in entry[subentries_name]:
                insert_entry(cur, subentries_table_name, plan_id, subentry)
                pbar.update()


def insert_entry(
    cur: sqlite3.Cursor,
    table: _EntryTable,
    plan_id: str,
    entry: dict[str, Any],
) -> None:
    ekeys, evalues = zip(*entry.items(), strict=True)
    keys, values = ekeys + ("plan_id",), evalues + (plan_id,)

    cur.execute(
        f"INSERT OR REPLACE INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(values))})",
        values,
    )


def jobs(
    yc: SupportsYnabClient,
    endpoint: (
        Literal["accounts"]
        | Literal["categories"]
        | Literal["payees"]
        | Literal["transactions"]
        | Literal["scheduled_transactions"]
    ),
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


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))
