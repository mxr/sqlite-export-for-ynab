from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import fields
from datetime import date
from datetime import timedelta
from importlib import resources
from importlib.metadata import version
from itertools import batched
from pathlib import Path
from typing import Any
from typing import Literal
from typing import overload
from typing import override
from typing import TYPE_CHECKING

import aiosqlite
import asyncio_for_ynab  # noqa: F401
import fasteners
from aiopathlib import AsyncPath
from asyncio_for_ynab import Account
from asyncio_for_ynab import AccountsApi
from asyncio_for_ynab import ApiClient
from asyncio_for_ynab import CategoriesApi
from asyncio_for_ynab import CategoryGroupWithCategories
from asyncio_for_ynab import Configuration
from asyncio_for_ynab import Payee
from asyncio_for_ynab import PayeesApi
from asyncio_for_ynab import PlansApi
from asyncio_for_ynab import PlanSummary
from asyncio_for_ynab import ScheduledTransactionDetail
from asyncio_for_ynab import ScheduledTransactionsApi
from asyncio_for_ynab import TransactionDetail
from asyncio_for_ynab import TransactionsApi
from asyncio_for_ynab import TransactionsResponse
from asyncio_for_ynab import TransactionsResponseData
from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import TaskID
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from tenacity import retry
from tenacity import stop_after_attempt

from sqlite_export_for_ynab import ddl

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from collections.abc import Awaitable
    from collections.abc import Callable
    from collections.abc import Iterator
    from collections.abc import Sequence

try:
    from rich.progress import MofNCompleteColumn
# https://github.com/benleb/surepy/issues/240
except ImportError:  # pragma: no cover
    from rich.progress import ProgressColumn
    from rich.progress import Task
    from rich.text import Text

    if TYPE_CHECKING:
        from rich.table import Column

    class MofNCompleteColumn(ProgressColumn):  # type:ignore[no-redef]
        def __init__(self, separator: str = "/", table_column: Column | None = None):
            self.separator = separator
            super().__init__(table_column=table_column)

        @override
        def render(self, task: Task) -> Text:
            """Show completed/total."""
            completed = int(task.completed)
            total = int(task.total) if task.total is not None else "?"
            total_width = len(str(total))
            return Text(
                f"{completed:{total_width}d}{self.separator}{total}",
                style="progress.download",
            )


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
_SYNC_LOCK_TIMEOUT = 30.0

_PROGRESS_COLUMNS = (
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
)


def resolve_token(token_override: str | None = None) -> str:
    token = token_override or os.environ.get(_ENV_TOKEN)
    if token:
        return token

    raise ValueError(
        f"Must set YNAB access token as {_ENV_TOKEN!r} environment variable or pass "
        "token_override directly. See https://api.ynab.com/#personal-access-tokens"
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


@dataclass
class _Context:
    progress: Progress
    con: aiosqlite.Connection
    lock: fasteners.InterProcessLock
    api_client: ApiClient


@dataclass
class _YnabPlanData:
    accounts: list[Account]
    category_groups: list[CategoryGroupWithCategories]
    payees: list[Payee]
    transactions: list[TransactionDetail]
    server_knowledge: int
    scheduled_transactions: list[ScheduledTransactionDetail]

    def has_data(self) -> bool:
        return any(
            getattr(self, field.name)
            for field in fields(self)
            if field.name != "server_knowledge"
        )


@asynccontextmanager
async def _context(
    db: Path,
    configuration: Configuration,
    *,
    quiet: bool,
    timeout: float = _SYNC_LOCK_TIMEOUT,
) -> AsyncIterator[_Context]:
    progress = Progress(*_PROGRESS_COLUMNS, disable=quiet)
    lock_path = db.parent / f"{db.name}.lock"
    lock = fasteners.InterProcessLock(lock_path)
    # ApiClient's constructor builds an SSL context (loads certs from disk),
    # so build it off the event loop thread.
    api_client = await asyncio.to_thread(ApiClient, configuration)
    async with (
        api_client,
        aiosqlite.connect(db) as con,
    ):
        con.row_factory = aiosqlite.Row
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        _print("Acquiring lock...", quiet=quiet)
        while True:
            acquired = await asyncio.to_thread(lock.acquire, False)
            if acquired:
                _print("Done", quiet=quiet)
                break
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting {timeout} seconds for sync lock at {lock.path}"
                )
            await asyncio.sleep(0.1)

        try:
            yield _Context(progress, con, lock, api_client)
        finally:
            try:
                await asyncio.to_thread(lock.release)
            finally:
                await AsyncPath(lock_path).unlink(missing_ok=True)


@contextmanager
def _progress(context: _Context) -> Iterator[None]:
    context.progress.start()
    try:
        yield
    finally:
        context.progress.stop()
        for task_id in context.progress.task_ids:
            context.progress.remove_task(task_id)


async def sync(
    token: str, db: Path, full_refresh: bool, *, quiet: bool = False
) -> None:
    await AsyncPath(db).parent.mkdir(parents=True, exist_ok=True)

    configuration = Configuration(access_token=token)
    async with _context(
        db, configuration, quiet=quiet, timeout=_SYNC_LOCK_TIMEOUT
    ) as context:
        plans = await _get_plan_summaries(context.api_client)

        if full_refresh:
            _print("Dropping relations...", quiet=quiet)
            async with context.con.cursor() as cur:
                await cur.executescript(await contents("drop-relations.sql"))
            await context.con.commit()
            _print("Done", quiet=quiet)

        async with context.con.cursor() as cur:
            relations = await get_relations(cur)
            if relations != _ALL_RELATIONS:
                _print("Recreating relations...", quiet=quiet)
                await cur.executescript(await contents("create-relations.sql"))
                await context.con.commit()
                _print("Done", quiet=quiet)

        _print("Fetching plan data...", quiet=quiet)
        async with context.con.cursor() as cur:
            lkos = await get_last_knowledge_of_server(cur)
        with _progress(context):
            task = context.progress.add_task(
                "Plan Data", total=len(plans) * len(_ENDPOINTS)
            )

            all_data = await _get_all_ynab(context, plans, lkos, task)

        _print("Done", quiet=quiet)

        if any(plan_data.has_data() for plan_data in all_data.values()):
            _print("Inserting plan data...", quiet=quiet)
            with _progress(context):
                await insert_plan_data(context, plans, all_data)
                await context.con.commit()
            _print("Done", quiet=quiet)
        else:
            _print("No new data fetched", quiet=quiet)


async def contents(filename: str) -> str:
    return await AsyncPath(str(resources.files(ddl) / filename)).read_text()


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
    context: _Context, plans: list[PlanSummary], all_data: dict[str, _YnabPlanData]
) -> None:
    await insert_plans(
        context,
        plans,
        {plan_id: d.server_knowledge for plan_id, d in all_data.items()},
    )
    await asyncio.gather(
        *(
            asyncio.gather(
                insert_accounts(context, plan_id, all_data[plan_id].accounts),
                insert_category_groups(
                    context, plan_id, all_data[plan_id].category_groups
                ),
                insert_payees(context, plan_id, all_data[plan_id].payees),
            )
            for plan_id in all_data
        ),
    )
    await asyncio.gather(
        *(
            asyncio.gather(
                insert_transactions(context, plan_id, all_data[plan_id].transactions),
                insert_scheduled_transactions(
                    context, plan_id, all_data[plan_id].scheduled_transactions
                ),
            )
            for plan_id in all_data
        ),
    )


async def insert_plans(
    context: _Context, plans: list[PlanSummary], lkos: dict[str, int]
) -> None:
    async with context.con.cursor() as cur:
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
                        plan_id := str(plan.id),
                        plan.name,
                        getattr(cf := plan.currency_format, "currency_symbol", None),
                        getattr(cf, "decimal_digits", None),
                        getattr(cf, "decimal_separator", None),
                        getattr(cf, "display_symbol", None),
                        getattr(cf, "group_separator", None),
                        getattr(cf, "iso_code", None),
                        getattr(cf, "symbol_first", None),
                        lkos[plan_id],
                    )
                    for plan in plan_batch
                ),
            )


_LOAN_ACCOUNT_PERIODIC_VALUES = frozenset(
    ("debt_escrow_amounts", "debt_interest_rates", "debt_minimum_payments")
)


async def insert_accounts(
    context: _Context,
    plan_id: str,
    accounts: list[Account],
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
        for account in (acc.model_dump(mode="json") for acc in accounts)
    ]

    await insert_nested_entries(
        context,
        plan_id,
        updated_accounts,
        "Accounts",
        "accounts",
        "account_periodic_values",
        "account_periodic_values",
    )


async def insert_category_groups(
    context: _Context,
    plan_id: str,
    category_groups: list[CategoryGroupWithCategories],
) -> None:
    await insert_nested_entries(
        context,
        plan_id,
        [cg.model_dump(mode="json") for cg in category_groups],
        "Categories",
        "category_groups",
        "categories",
        "categories",
    )


async def insert_payees(
    context: _Context,
    plan_id: str,
    payees: list[Payee],
) -> None:
    if not payees:
        return

    task_id = context.progress.add_task("Payees", total=len(payees))
    await insert_entries(
        context, "payees", plan_id, [p.model_dump(mode="json") for p in payees], task_id
    )


async def insert_transactions(
    context: _Context,
    plan_id: str,
    transactions: list[TransactionDetail],
) -> None:
    await insert_nested_entries(
        context,
        plan_id,
        # by_alias=True properly renames 'var_date' to 'date'
        [t.model_dump(mode="json", by_alias=True) for t in transactions],
        "Transactions",
        "transactions",
        "subtransactions",
        "subtransactions",
    )


async def insert_scheduled_transactions(
    context: _Context,
    plan_id: str,
    scheduled_transactions: list[ScheduledTransactionDetail],
) -> None:
    await insert_nested_entries(
        context,
        plan_id,
        [st.model_dump(mode="json") for st in scheduled_transactions],
        "Scheduled Transactions",
        "scheduled_transactions",
        "subtransactions",
        "scheduled_subtransactions",
    )


@overload
async def insert_nested_entries(
    context: _Context,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Accounts"],
    entries_name: Literal["accounts"],
    subentries_name: Literal["account_periodic_values"],
    subentries_table_name: Literal["account_periodic_values"],
) -> None: ...


@overload
async def insert_nested_entries(
    context: _Context,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Categories"],
    entries_name: Literal["category_groups"],
    subentries_name: Literal["categories"],
    subentries_table_name: Literal["categories"],
) -> None: ...


@overload
async def insert_nested_entries(
    context: _Context,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Transactions"],
    entries_name: Literal["transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["subtransactions"],
) -> None: ...


@overload
async def insert_nested_entries(
    context: _Context,
    plan_id: str,
    entries: list[dict[str, Any]],
    desc: Literal["Scheduled Transactions"],
    entries_name: Literal["scheduled_transactions"],
    subentries_name: Literal["subtransactions"],
    subentries_table_name: Literal["scheduled_subtransactions"],
) -> None: ...


async def insert_nested_entries(
    context: _Context,
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

    task_id = context.progress.add_task(
        desc, total=sum(1 + len(e[subentries_name]) for e in entries)
    )
    await insert_entries(
        context,
        entries_name,
        plan_id,
        [{k: v for k, v in entry.items() if k != subentries_name} for entry in entries],
        task_id,
    )
    await insert_entries(
        context,
        subentries_table_name,
        plan_id,
        [subentry for entry in entries for subentry in entry[subentries_name]],
        task_id,
    )


async def insert_entries(
    context: _Context,
    table: _EntryTable,
    plan_id: str,
    entries: list[dict[str, Any]],
    task_id: TaskID,
) -> None:
    if not entries:
        return

    async with context.con.cursor() as cur:
        await cur.execute(f"PRAGMA table_info({table})")
        table_columns = {row["name"] async for row in cur}

    # Ignore any keys the YNAB API returns that aren't columns in the DDL so
    # newly-added API fields don't break the insert.
    entry_keys = tuple(k for k in entries[0] if k in table_columns)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(entry_keys + ('plan_id',))}) VALUES ({', '.join('?' * (len(entry_keys) + 1))})"

    async with context.con.cursor() as cur:
        for entry_batch in batched(entries, _BATCH_SIZE):
            values_batch = [
                tuple(entry[key] for key in entry_keys) + (plan_id,)
                for entry in entry_batch
            ]
            await cur.executemany(sql, values_batch)
            context.progress.update(task_id, advance=len(values_batch))


@retry(stop=stop_after_attempt(3))
async def _get_plan_summaries(api_client: ApiClient) -> list[PlanSummary]:
    return (await PlansApi(api_client).get_plans()).data.plans


async def _get_all_ynab(
    context: _Context, plans: list[PlanSummary], lkos: dict[str, int], task_id: TaskID
) -> dict[str, _YnabPlanData]:
    return dict(
        await asyncio.gather(
            *(_get_plan_data(context, plan, lkos, task_id) for plan in plans)
        )
    )


async def _get_plan_data(
    context: _Context, plan: PlanSummary, lkos: dict[str, int], task_id: TaskID
) -> tuple[str, _YnabPlanData]:
    plan_id = str(plan.id)
    assert plan.first_month is not None
    py = _ProgressYnab(context, plan_id, lkos, task_id)
    accounts, categories, payees, transactions, scheduled = await asyncio.gather(
        py.get(AccountsApi(context.api_client).get_accounts),
        py.get(CategoriesApi(context.api_client).get_categories),
        py.get(PayeesApi(context.api_client).get_payees),
        py.get(
            ChunkedTransactionsApi(
                context.api_client, plan.first_month
            ).get_transactions
        ),
        py.get(ScheduledTransactionsApi(context.api_client).get_scheduled_transactions),
    )
    return (
        plan_id,
        _YnabPlanData(
            accounts=accounts.data.accounts,
            category_groups=categories.data.category_groups,
            payees=payees.data.payees,
            transactions=transactions.data.transactions,
            server_knowledge=transactions.data.server_knowledge,
            scheduled_transactions=scheduled.data.scheduled_transactions,
        ),
    )


@dataclass(slots=True)
class _ProgressYnab:
    context: _Context
    plan_id: str
    lkos: dict[str, int]
    task_id: TaskID

    @retry(stop=stop_after_attempt(3))
    async def get[T](self, endpoint: Callable[..., Awaitable[T]]) -> T:
        try:
            return await endpoint(
                plan_id=self.plan_id,
                last_knowledge_of_server=self.lkos.get(self.plan_id),
            )
        finally:
            self.context.progress.update(self.task_id, advance=1)


@dataclass(slots=True, frozen=True)
class ChunkedTransactionsApi:
    api_client: ApiClient
    first_month: date

    async def get_transactions(
        self, *, plan_id: str, last_knowledge_of_server: int | None
    ) -> TransactionsResponse:
        transactions_api = TransactionsApi(self.api_client)
        if last_knowledge_of_server is not None:
            return await transactions_api.get_transactions(
                plan_id=plan_id,
                last_knowledge_of_server=last_knowledge_of_server,
            )
        return await self._get(transactions_api, plan_id)

    async def _get(
        self, transactions_api: TransactionsApi, plan_id: str
    ) -> TransactionsResponse:
        today = date.today()
        responses = await asyncio.gather(
            *(
                self._chunk(transactions_api, plan_id, since_date, until_date)
                for since_date, until_date in _quarterly(self.first_month, today)
            )
        )
        transactions = [
            transaction
            for response in responses
            for transaction in response.data.transactions
        ]
        ids = [transaction.id for transaction in transactions]
        assert len(set(ids)) == len(ids)  # paranoid check for no overlap across chunks
        return TransactionsResponse(
            data=TransactionsResponseData(
                transactions=transactions,
                server_knowledge=max(
                    response.data.server_knowledge for response in responses
                ),
            )
        )

    @retry(stop=stop_after_attempt(3))
    async def _chunk(
        self,
        transactions_api: TransactionsApi,
        plan_id: str,
        since_date: date,
        until_date: date,
    ) -> TransactionsResponse:
        return await transactions_api.get_transactions(
            plan_id=plan_id,
            since_date=since_date,
            until_date=until_date,
        )


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    return date(d.year + month_index // 12, month_index % 12 + 1, 1)


def _quarterly(first_month: date, today: date) -> Iterator[tuple[date, date]]:
    since_date = first_month
    while since_date <= today:
        until_date = min(_add_months(since_date, 3) - timedelta(days=1), today)
        yield since_date, until_date
        since_date = until_date + timedelta(days=1)


def main(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    return asyncio.run(async_main(argv, token_override=token_override))
