from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from importlib import resources
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
from tqdm import tqdm

from sqlite_export_for_ynab import ddl

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from typing import Never


_EntryTable = (
    Literal["category_groups"]
    | Literal["categories"]
    | Literal["payees"]
    | Literal["transactions"]
    | Literal["subtransactions"]
)
_ALL_TABLES = frozenset(
    ("budgets",) + tuple(lit.__args__[0] for lit in _EntryTable.__args__)
)

_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        help="The path to the SQLite database file.",
        type=Path,
        default=default_db_path(),
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="**DROP ALL TABLES** and fetch all budget data again.",
    )

    args = parser.parse_args()
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
        / "sqlite-export-for-ynab"
        / "db.sqlite"
    )


async def sync(token: str, db: Path, full_refresh: bool) -> None:
    async with aiohttp.ClientSession() as session:
        budgets = (await YnabClient(token, session)("budgets"))["budgets"]

    budget_ids = [b["id"] for b in budgets]

    if not db.exists():
        db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as con:
        con.row_factory = lambda c, row: dict(
            zip([name for name, *_ in c.description], row, strict=True)
        )
        cur = con.cursor()

        if full_refresh:
            print("Dropping tables...")
            cur.executescript(contents("drop-tables.sqlite"))
            con.commit()
            print("Done")

        tables = get_tables(cur)
        if tables != _ALL_TABLES:
            print("Recreating tables...")
            cur.executescript(contents("create-tables.sqlite"))
            con.commit()
            print("Done")

        print("Fetching budget data...")
        lkos = get_last_knowledge_of_server(cur)
        async with aiohttp.ClientSession() as session:
            with tqdm(desc="Budget Data", total=len(budgets) * 3) as pbar:
                yc = ProgressYnabClient(
                    YnabClient(os.environ["YNAB_PERSONAL_ACCESS_TOKEN"], session), pbar
                )

                cat_jobs = jobs(yc, "categories", budget_ids, lkos)
                payee_jobs = jobs(yc, "payees", budget_ids, lkos)
                txn_jobs = jobs(yc, "transactions", budget_ids, lkos)

                data = await asyncio.gather(*cat_jobs, *payee_jobs, *txn_jobs)

            lc = len(cat_jobs)
            lp = len(payee_jobs)

            all_cat_data = data[:lc]
            all_payee_data = data[lc : lc + lp]
            all_txn_data = data[lc + lp :]

            new_lkos = {
                bid: t["server_knowledge"]
                for bid, t in zip(budget_ids, all_txn_data, strict=True)
            }
        print("Done")

        if (
            not any(c["category_groups"] for c in all_cat_data)
            and not any(p["payees"] for p in all_payee_data)
            and not any(t["transactions"] for t in all_txn_data)
        ):
            print("No data fetched")
        else:
            print("Inserting budget data...")
            insert_budgets(cur, budgets, new_lkos)
            for bid, cat_data in zip(budget_ids, all_cat_data, strict=True):
                insert_category_groups(cur, bid, cat_data["category_groups"])
            for bid, payee_data in zip(budget_ids, all_payee_data, strict=True):
                insert_payees(cur, bid, payee_data["payees"])
            for bid, txn_data in zip(budget_ids, all_txn_data, strict=True):
                insert_transactions(cur, bid, txn_data["transactions"])
            print("Done")


def contents(filename: str) -> str:
    return (resources.files(ddl) / filename).read_text()


def get_tables(cur: sqlite3.Cursor) -> set[str]:
    return {
        t["name"]
        for t in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def get_last_knowledge_of_server(cur: sqlite3.Cursor) -> dict[str, int]:
    return {
        r["id"]: r["last_knowledge_of_server"]
        for r in cur.execute(
            "SELECT id, last_knowledge_of_server FROM budgets",
        ).fetchall()
    }


def insert_budgets(
    cur: sqlite3.Cursor, budgets: list[dict[str, Any]], lkos: dict[str, int]
) -> None:
    cur.executemany(
        "INSERT OR REPLACE INTO budgets (id, name, last_knowledge_of_server) VALUES (?, ?, ?)",
        ((bid := b["id"], b["name"], lkos[bid]) for b in budgets),
    )


def insert_category_groups(
    cur: sqlite3.Cursor, budget_id: str, category_groups: list[dict[str, Any]]
) -> None:
    return insert_nested_entries(
        cur, budget_id, category_groups, "Categories", "category_groups", "categories"
    )


def insert_payees(
    cur: sqlite3.Cursor, budget_id: str, payees: list[dict[str, Any]]
) -> None:
    if not payees:
        return

    for payee in tqdm(payees, desc="Payees"):
        insert_entry(cur, "payees", budget_id, payee)


def insert_transactions(
    cur: sqlite3.Cursor, budget_id: str, transactions: list[dict[str, Any]]
) -> None:
    return insert_nested_entries(
        cur, budget_id, transactions, "Transactions", "transactions", "subtransactions"
    )


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    budget_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Transactions"],
    entries_name: Literal["transactions"],
    subentries_name: Literal["subtransactions"],
) -> None: ...


@overload
def insert_nested_entries(
    cur: sqlite3.Cursor,
    budget_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Categories"],
    entries_name: Literal["category_groups"],
    subentries_name: Literal["categories"],
) -> None: ...


def insert_nested_entries(
    cur: sqlite3.Cursor,
    budget_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Transactions"] | Literal["Categories"],
    entries_name: Literal["transactions"] | Literal["category_groups"],
    subentries_name: Literal["subtransactions"] | Literal["categories"],
) -> None:
    if not entries:
        return

    with tqdm(
        total=sum(1 + len(e[subentries_name]) for e in entries),
        desc=desc,
    ) as pbar:
        for entry in entries:
            subentries = entry.pop(subentries_name, [])
            insert_entry(cur, entries_name, budget_id, entry)
            pbar.update()

            for subentry in subentries:
                insert_entry(cur, subentries_name, budget_id, subentry)
                pbar.update()


def insert_entry(
    cur: sqlite3.Cursor,
    table: _EntryTable,
    budget_id: str,
    entry: dict[str, Any],
) -> None:
    ekeys, evalues = zip(*entry.items(), strict=True)
    keys, values = ekeys + ("budget_id",), evalues + (budget_id,)

    cur.execute(
        f'INSERT OR REPLACE INTO {table} ({", ".join(keys)}) VALUES ({", ".join("?" * len(values))})',
        values,
    )


def jobs(
    yc: SupportsYnabClient,
    endpoint: Literal["transactions"] | Literal["categories"] | Literal["payees"],
    budget_ids: list[str],
    lkos: dict[str, int],
) -> list[Awaitable[dict[str, Any]]]:
    return [
        yc(f"budgets/{bid}/{endpoint}", last_knowledge_of_server=lkos.get(bid))
        for bid in budget_ids
    ]


class SupportsYnabClient(Protocol):
    async def __call__(
        self, path: str, last_knowledge_of_server: int | None = None
    ) -> dict[str, Any]: ...


@dataclass
class ProgressYnabClient:
    yc: YnabClient
    pbar: tqdm[Never]

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

        async with self.session.get(url, headers=headers) as resp:
            body = await resp.text()

        return json.loads(body)["data"]


def main() -> int:
    return asyncio.run(async_main())
