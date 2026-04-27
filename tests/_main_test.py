from __future__ import annotations

import asyncio
import json
from configparser import ConfigParser
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import aiohttp
import aiosqlite
import fasteners
import pytest
import pytest_asyncio
from aiohttp.http_exceptions import HttpProcessingError
from rich.progress import Progress

from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab._main import _ALL_RELATIONS
from sqlite_export_for_ynab._main import _Context
from sqlite_export_for_ynab._main import _context
from sqlite_export_for_ynab._main import _ENV_TOKEN
from sqlite_export_for_ynab._main import _PACKAGE
from sqlite_export_for_ynab._main import _PROGRESS_COLUMNS
from sqlite_export_for_ynab._main import contents
from sqlite_export_for_ynab._main import get_last_knowledge_of_server
from sqlite_export_for_ynab._main import get_relations
from sqlite_export_for_ynab._main import insert_accounts
from sqlite_export_for_ynab._main import insert_category_groups
from sqlite_export_for_ynab._main import insert_payees
from sqlite_export_for_ynab._main import insert_plans
from sqlite_export_for_ynab._main import insert_scheduled_transactions
from sqlite_export_for_ynab._main import insert_transactions
from sqlite_export_for_ynab._main import main
from sqlite_export_for_ynab._main import ProgressYnabClient
from sqlite_export_for_ynab._main import resolve_token
from sqlite_export_for_ynab._main import sync
from sqlite_export_for_ynab._main import YnabClient
from testing.fixtures import ACCOUNT_ID_1
from testing.fixtures import ACCOUNT_ID_2
from testing.fixtures import ACCOUNTS
from testing.fixtures import ACCOUNTS_ENDPOINT_RE
from testing.fixtures import CATEGORIES_ENDPOINT_RE
from testing.fixtures import CATEGORY_GOAL_TARGET_DATE_1
from testing.fixtures import CATEGORY_GROUP_ID_1
from testing.fixtures import CATEGORY_GROUP_ID_2
from testing.fixtures import CATEGORY_GROUP_NAME_1
from testing.fixtures import CATEGORY_GROUP_NAME_2
from testing.fixtures import CATEGORY_GROUPS
from testing.fixtures import CATEGORY_ID_1
from testing.fixtures import CATEGORY_ID_2
from testing.fixtures import CATEGORY_ID_3
from testing.fixtures import CATEGORY_ID_4
from testing.fixtures import CATEGORY_NAME_1
from testing.fixtures import CATEGORY_NAME_2
from testing.fixtures import CATEGORY_NAME_3
from testing.fixtures import CATEGORY_NAME_4
from testing.fixtures import EXAMPLE_ENDPOINT_RE
from testing.fixtures import LKOS
from testing.fixtures import mock_aioresponses
from testing.fixtures import PAYEE_ID_1
from testing.fixtures import PAYEE_ID_2
from testing.fixtures import PAYEES
from testing.fixtures import PAYEES_ENDPOINT_RE
from testing.fixtures import PLAN_ID_1
from testing.fixtures import PLAN_ID_2
from testing.fixtures import PLANS
from testing.fixtures import PLANS_ENDPOINT_RE
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_1
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTION_ID_1
from testing.fixtures import SCHEDULED_TRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTION_ID_3
from testing.fixtures import SCHEDULED_TRANSACTIONS
from testing.fixtures import SCHEDULED_TRANSACTIONS_ENDPOINT_RE
from testing.fixtures import SERVER_KNOWLEDGE_1
from testing.fixtures import strip_nones
from testing.fixtures import SUBTRANSACTION_ID_1
from testing.fixtures import SUBTRANSACTION_ID_2
from testing.fixtures import TOKEN
from testing.fixtures import TRANSACTION_ID_1
from testing.fixtures import TRANSACTION_ID_2
from testing.fixtures import TRANSACTION_ID_3
from testing.fixtures import TRANSACTIONS
from testing.fixtures import TRANSACTIONS_ENDPOINT_RE


async def fetchall(con, query):
    async with con.cursor() as cur:
        await cur.execute(query)
        return await cur.fetchall()


@pytest_asyncio.fixture
async def context(tmp_path):
    with Progress(*_PROGRESS_COLUMNS, disable=True) as progress:
        async with (
            aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session,
            aiosqlite.connect(":memory:") as con,
        ):
            con.row_factory = aiosqlite.Row
            await con.executescript(await contents("create-relations.sql"))
            lock = fasteners.InterProcessLock(
                tmp_path / "sqlite-export-for-ynab-test.lock"
            )
            yield _Context(session, progress, con, lock)


@pytest.mark.parametrize(
    ("xdg_data_home", "expected_prefix"),
    (
        ("/tmp", Path("/tmp")),
        ("", Path.home() / ".local" / "share"),
    ),
)
def test_default_db_path(monkeypatch, xdg_data_home, expected_prefix):
    monkeypatch.setenv("XDG_DATA_HOME", xdg_data_home)
    assert default_db_path() == expected_prefix / "sqlite-export-for-ynab" / "db.sqlite"


@pytest.mark.asyncio
async def test_get_relations(context):
    async with context.con.cursor() as cur:
        assert await get_relations(cur) == _ALL_RELATIONS


@pytest.mark.asyncio
async def test_get_last_knowledge_of_server(context):
    await insert_plans(context, PLANS, LKOS)
    async with context.con.cursor() as cur:
        assert await get_last_knowledge_of_server(cur) == LKOS


@pytest.mark.asyncio
async def test_insert_plans(context):
    await insert_plans(context, PLANS, LKOS)
    assert [
        strip_nones(d)
        for d in await fetchall(context.con, "SELECT * FROM plans ORDER BY name")
    ] == [
        {
            "id": PLAN_ID_1,
            "name": PLANS[0]["name"],
            "currency_format_currency_symbol": "$",
            "currency_format_decimal_digits": 2,
            "currency_format_decimal_separator": ".",
            "currency_format_display_symbol": 1,
            "currency_format_group_separator": ",",
            "currency_format_iso_code": "USD",
            "currency_format_symbol_first": 1,
            "last_knowledge_of_server": LKOS[PLAN_ID_1],
        },
        {
            "id": PLAN_ID_2,
            "name": PLANS[1]["name"],
            "currency_format_currency_symbol": "$",
            "currency_format_decimal_digits": 2,
            "currency_format_decimal_separator": ".",
            "currency_format_display_symbol": 1,
            "currency_format_group_separator": ",",
            "currency_format_iso_code": "USD",
            "currency_format_symbol_first": 1,
            "last_knowledge_of_server": LKOS[PLAN_ID_2],
        },
    ]


@pytest.mark.asyncio
async def test_insert_accounts(context):
    await insert_accounts(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM accounts")
    assert not await fetchall(context.con, "SELECT * FROM account_periodic_values")

    await insert_accounts(context, PLAN_ID_1, ACCOUNTS)
    assert [
        strip_nones(d)
        for d in await fetchall(context.con, "SELECT * FROM accounts ORDER BY name")
    ] == [
        {
            "id": ACCOUNT_ID_1,
            "plan_id": PLAN_ID_1,
            "name": ACCOUNTS[0]["name"],
            "type": ACCOUNTS[0]["type"],
            "balance_formatted": "$160.00",
            "balance_currency": 160.0,
            "cleared_balance_formatted": "$120.00",
            "cleared_balance_currency": 120.0,
            "uncleared_balance_formatted": "$40.00",
            "uncleared_balance_currency": 40.0,
        },
        {
            "id": ACCOUNT_ID_2,
            "plan_id": PLAN_ID_1,
            "name": ACCOUNTS[1]["name"],
            "type": ACCOUNTS[1]["type"],
            "balance_formatted": "$25.00",
            "balance_currency": 25.0,
            "cleared_balance_formatted": "$25.00",
            "cleared_balance_currency": 25.0,
            "uncleared_balance_formatted": "$0.00",
            "uncleared_balance_currency": 0.0,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM account_periodic_values ORDER BY name"
        )
    ] == [
        {
            "account_id": ACCOUNT_ID_1,
            "plan_id": PLAN_ID_1,
            "name": "debt_escrow_amounts",
            "date": "2024-01-01",
            "amount": 160000,
        },
        {
            "account_id": ACCOUNT_ID_1,
            "plan_id": PLAN_ID_1,
            "name": "debt_interest_rates",
            "date": "2024-02-01",
            "amount": 5000,
        },
    ]


@pytest.mark.asyncio
async def test_insert_category_groups(context):
    await insert_category_groups(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM category_groups")
    assert not await fetchall(context.con, "SELECT * FROM categories")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM category_groups ORDER BY name"
        )
    ] == [
        {
            "id": CATEGORY_GROUP_ID_1,
            "name": CATEGORY_GROUP_NAME_1,
            "plan_id": PLAN_ID_1,
        },
        {
            "id": CATEGORY_GROUP_ID_2,
            "name": CATEGORY_GROUP_NAME_2,
            "plan_id": PLAN_ID_1,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(context.con, "SELECT * FROM categories ORDER BY name")
    ] == [
        {
            "id": CATEGORY_ID_1,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "category_group_name": CATEGORY_GROUP_NAME_1,
            "plan_id": PLAN_ID_1,
            "name": CATEGORY_NAME_1,
            "balance_formatted": "$12.00",
            "balance_currency": 12.0,
            "activity_formatted": "$2.50",
            "activity_currency": 2.5,
            "budgeted_formatted": "$14.50",
            "budgeted_currency": 14.5,
            "goal_target_formatted": "$20.00",
            "goal_target_currency": 20.0,
            "goal_target_date": CATEGORY_GOAL_TARGET_DATE_1,
            "goal_under_funded_formatted": "$8.00",
            "goal_under_funded_currency": 8.0,
            "goal_overall_funded_formatted": "$12.00",
            "goal_overall_funded_currency": 12.0,
            "goal_overall_left_formatted": "$8.00",
            "goal_overall_left_currency": 8.0,
        },
        {
            "id": CATEGORY_ID_2,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "category_group_name": CATEGORY_GROUP_NAME_1,
            "plan_id": PLAN_ID_1,
            "name": CATEGORY_NAME_2,
            "balance_formatted": "$9.25",
            "balance_currency": 9.25,
            "activity_formatted": "$1.00",
            "activity_currency": 1.0,
            "budgeted_formatted": "$10.25",
            "budgeted_currency": 10.25,
        },
        {
            "id": CATEGORY_ID_3,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "category_group_name": CATEGORY_GROUP_NAME_2,
            "plan_id": PLAN_ID_1,
            "name": CATEGORY_NAME_3,
            "balance_formatted": "$7.50",
            "balance_currency": 7.5,
            "activity_formatted": "$7.50",
            "activity_currency": 7.5,
            "budgeted_formatted": "$15.00",
            "budgeted_currency": 15.0,
        },
        {
            "id": CATEGORY_ID_4,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "category_group_name": CATEGORY_GROUP_NAME_2,
            "plan_id": PLAN_ID_1,
            "name": CATEGORY_NAME_4,
            "balance_formatted": "$19.00",
            "balance_currency": 19.0,
            "activity_formatted": "$19.00",
            "activity_currency": 19.0,
            "budgeted_formatted": "$20.00",
            "budgeted_currency": 20.0,
        },
    ]


@pytest.mark.asyncio
async def test_insert_category_group_without_categories(context):
    category_group = {
        "id": CATEGORY_GROUP_ID_1,
        "name": CATEGORY_GROUP_NAME_1,
        "categories": [],
    }

    await insert_category_groups(context, PLAN_ID_1, [category_group])

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM category_groups ORDER BY name"
        )
    ] == [
        {
            "id": CATEGORY_GROUP_ID_1,
            "name": CATEGORY_GROUP_NAME_1,
            "plan_id": PLAN_ID_1,
        },
    ]
    assert not await fetchall(context.con, "SELECT * FROM categories")


@pytest.mark.asyncio
async def test_insert_payees(context):
    await insert_payees(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM payees")

    await insert_payees(context, PLAN_ID_1, PAYEES)
    assert [
        strip_nones(d)
        for d in await fetchall(context.con, "SELECT * FROM payees ORDER BY name")
    ] == [
        {
            "id": PAYEE_ID_1,
            "plan_id": PLAN_ID_1,
            "name": PAYEES[0]["name"],
        },
        {
            "id": PAYEE_ID_2,
            "plan_id": PLAN_ID_1,
            "name": PAYEES[1]["name"],
        },
    ]


@pytest.mark.asyncio
async def test_insert_transactions(context):
    await insert_transactions(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM transactions")
    assert not await fetchall(context.con, "SELECT * FROM subtransactions")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    await insert_transactions(context, PLAN_ID_1, TRANSACTIONS)
    assert [
        strip_nones(d)
        for d in await fetchall(context.con, "SELECT * FROM transactions ORDER BY date")
    ] == [
        {
            "id": TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "date": "2024-01-01",
            "amount": -10000,
            "amount_formatted": "$10.00",
            "amount_currency": 10.0,
            "approved": 1,
            "category_id": CATEGORY_ID_3,
            "category_name": CATEGORY_NAME_3,
            "deleted": False,
        },
        {
            "id": TRANSACTION_ID_2,
            "plan_id": PLAN_ID_1,
            "date": "2024-02-01",
            "amount": -15000,
            "amount_formatted": "$15.00",
            "amount_currency": 15.0,
            "approved": 1,
            "category_id": CATEGORY_ID_2,
            "category_name": CATEGORY_NAME_2,
            "deleted": True,
        },
        {
            "id": TRANSACTION_ID_3,
            "plan_id": PLAN_ID_1,
            "date": "2024-03-01",
            "amount": -19000,
            "amount_formatted": "$19.00",
            "amount_currency": 19.0,
            "approved": 0,
            "category_id": CATEGORY_ID_4,
            "category_name": CATEGORY_NAME_4,
            "deleted": False,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM subtransactions ORDER BY amount"
        )
    ] == [
        {
            "id": SUBTRANSACTION_ID_1,
            "transaction_id": TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "amount": -7500,
            "amount_formatted": "$7.50",
            "amount_currency": 7.5,
            "category_id": CATEGORY_ID_1,
            "category_name": CATEGORY_NAME_1,
            "deleted": False,
        },
        {
            "id": SUBTRANSACTION_ID_2,
            "transaction_id": TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "amount": -2500,
            "amount_formatted": "$2.50",
            "amount_currency": 2.5,
            "category_id": CATEGORY_ID_2,
            "category_name": CATEGORY_NAME_2,
            "deleted": False,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM flat_transactions ORDER BY amount"
        )
    ] == [
        {
            "transaction_id": TRANSACTION_ID_1,
            "subtransaction_id": SUBTRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "date": "2024-01-01",
            "id": SUBTRANSACTION_ID_1,
            "amount": -7500,
            "amount_formatted": "$7.50",
            "amount_currency": 7.5,
            "category_id": CATEGORY_ID_1,
            "category_name": CATEGORY_NAME_1,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "category_group_name": CATEGORY_GROUP_NAME_1,
        },
        {
            "transaction_id": TRANSACTION_ID_1,
            "subtransaction_id": SUBTRANSACTION_ID_2,
            "plan_id": PLAN_ID_1,
            "date": "2024-01-01",
            "id": SUBTRANSACTION_ID_2,
            "amount": -2500,
            "amount_formatted": "$2.50",
            "amount_currency": 2.5,
            "category_id": CATEGORY_ID_2,
            "category_name": CATEGORY_NAME_2,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "category_group_name": CATEGORY_GROUP_NAME_1,
        },
    ]


@pytest.mark.asyncio
async def test_insert_scheduled_transactions(context):
    await insert_scheduled_transactions(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM scheduled_transactions")
    assert not await fetchall(context.con, "SELECT * FROM scheduled_subtransactions")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    await insert_scheduled_transactions(context, PLAN_ID_1, SCHEDULED_TRANSACTIONS)
    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM scheduled_transactions ORDER BY amount"
        )
    ] == [
        {
            "id": SCHEDULED_TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "frequency": "monthly",
            "amount": -12000,
            "amount_formatted": "$12.00",
            "amount_currency": 12.0,
            "category_id": CATEGORY_ID_1,
            "category_name": CATEGORY_NAME_1,
            "deleted": False,
        },
        {
            "id": SCHEDULED_TRANSACTION_ID_2,
            "plan_id": PLAN_ID_1,
            "frequency": "yearly",
            "amount": -11000,
            "amount_formatted": "$11.00",
            "amount_currency": 11.0,
            "category_id": CATEGORY_ID_3,
            "category_name": CATEGORY_NAME_3,
            "deleted": True,
        },
        {
            "id": SCHEDULED_TRANSACTION_ID_3,
            "plan_id": PLAN_ID_1,
            "frequency": "everyOtherMonth",
            "amount": -9000,
            "amount_formatted": "$9.00",
            "amount_currency": 9.0,
            "category_id": CATEGORY_ID_4,
            "category_name": CATEGORY_NAME_4,
            "deleted": False,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM scheduled_subtransactions ORDER BY amount"
        )
    ] == [
        {
            "id": SCHEDULED_SUBTRANSACTION_ID_1,
            "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "amount": -8040,
            "amount_formatted": "$8.04",
            "amount_currency": 8.04,
            "category_id": CATEGORY_ID_2,
            "category_name": CATEGORY_NAME_2,
            "deleted": False,
        },
        {
            "id": SCHEDULED_SUBTRANSACTION_ID_2,
            "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "amount": -2960,
            "amount_formatted": "$2.96",
            "amount_currency": 2.96,
            "category_id": CATEGORY_ID_3,
            "category_name": CATEGORY_NAME_3,
            "deleted": False,
        },
    ]

    assert [
        strip_nones(d)
        for d in await fetchall(
            context.con, "SELECT * FROM scheduled_flat_transactions ORDER BY amount"
        )
    ] == [
        {
            "transaction_id": SCHEDULED_TRANSACTION_ID_3,
            "plan_id": PLAN_ID_1,
            "id": SCHEDULED_TRANSACTION_ID_3,
            "frequency": "everyOtherMonth",
            "amount": -9000,
            "amount_formatted": "$9.00",
            "amount_currency": 9.0,
            "category_id": CATEGORY_ID_4,
            "category_name": CATEGORY_NAME_4,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "category_group_name": CATEGORY_GROUP_NAME_2,
        },
        {
            "transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_1,
            "plan_id": PLAN_ID_1,
            "id": SCHEDULED_SUBTRANSACTION_ID_1,
            "frequency": "monthly",
            "amount": -8040,
            "amount_formatted": "$8.04",
            "amount_currency": 8.04,
            "category_id": CATEGORY_ID_2,
            "category_name": CATEGORY_NAME_2,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "category_group_name": CATEGORY_GROUP_NAME_1,
        },
        {
            "transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_2,
            "plan_id": PLAN_ID_1,
            "id": SCHEDULED_SUBTRANSACTION_ID_2,
            "frequency": "monthly",
            "amount": -2960,
            "amount_formatted": "$2.96",
            "amount_currency": 2.96,
            "category_id": CATEGORY_ID_3,
            "category_name": CATEGORY_NAME_3,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "category_group_name": CATEGORY_GROUP_NAME_2,
        },
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_progress_ynab_client_ok(context, mock_aioresponses):
    expected = {"example": [{"id": 1, "value": 2}, {"id": 3, "value": 4}]}
    mock_aioresponses.get(EXAMPLE_ENDPOINT_RE, body=json.dumps({"data": expected}))

    task_id = context.progress.add_task("Example", total=1)
    pyc = ProgressYnabClient(YnabClient(TOKEN, context.session), context, task_id)
    entries = await pyc("example")

    assert entries == expected


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_ynab_client_failure(mock_aioresponses):
    exc = HttpProcessingError(code=500)
    mock_aioresponses.get(EXAMPLE_ENDPOINT_RE, exception=exc, repeat=True)

    with pytest.raises(type(exc)) as excinfo:
        async with aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session:
            await YnabClient(TOKEN, session)("example")

    assert excinfo.value == exc


def test_main_version(capsys):
    cp = ConfigParser()
    cp.read(Path(__file__).parent.parent / "setup.cfg")
    expected_version = cp["metadata"]["version"]

    with pytest.raises(SystemExit) as excinfo:
        main(("--version",))
    assert excinfo.value.code == 0

    out, _ = capsys.readouterr()
    assert out == f"{_PACKAGE} {expected_version}\n"


@patch("sqlite_export_for_ynab._main.sync")
def test_main_ok(sync, tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = main(("--db", str(tmp_path / "db.sqlite")))
    sync.assert_called_once_with(TOKEN, tmp_path / "db.sqlite", False, quiet=False)
    assert ret == 0


def test_main_no_token(tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError):
        main(("--db", str(tmp_path / "db.sqlite")))


@patch("sqlite_export_for_ynab._main.sync")
def test_main_uses_token_override(sync, tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV_TOKEN, raising=False)

    ret = main(("--db", str(tmp_path / "db.sqlite")), token_override="override-token")

    sync.assert_called_once_with(
        "override-token", tmp_path / "db.sqlite", False, quiet=False
    )
    assert ret == 0


@patch("sqlite_export_for_ynab._main.sync")
def test_main_quiet(sync, tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = main(("--db", str(tmp_path / "db.sqlite"), "--quiet"))

    sync.assert_called_once_with(TOKEN, tmp_path / "db.sqlite", False, quiet=True)
    assert ret == 0


def test_resolve_token_override(monkeypatch):
    monkeypatch.delenv(_ENV_TOKEN, raising=False)

    assert resolve_token("override-token") == "override-token"


def test_resolve_token_env(monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    assert resolve_token() == TOKEN


@patch(
    "sqlite_export_for_ynab._main.fasteners.InterProcessLock.acquire",
    autospec=True,
    return_value=False,
)
@patch("sqlite_export_for_ynab._main.asyncio.get_running_loop")
@patch("sqlite_export_for_ynab._main.aiohttp.ClientSession")
@pytest.mark.asyncio
async def test_sync_lock_times_out(
    mock_client_session, mock_get_running_loop, mock_acquire, tmp_path
):
    class FakeLoop:
        def __init__(self):
            self._times = iter((0.0, 0.2))

        def time(self):
            return next(self._times)

    mock_get_running_loop.return_value = FakeLoop()

    @asynccontextmanager
    async def fake_client_session():
        yield object()

    mock_client_session.return_value = fake_client_session()

    with pytest.raises(TimeoutError):
        async with _context(tmp_path / "db.sqlite", quiet=True, timeout=0.1):
            pass

    assert mock_acquire.call_count == 1
    assert mock_acquire.call_args.args[1] is False


@pytest.mark.asyncio
async def test_context_removes_lock_file(tmp_path):
    db = tmp_path / "db.sqlite"
    lock_path = tmp_path / "db.sqlite.lock"

    async with _context(db, quiet=True):
        assert lock_path.exists()

    assert not lock_path.exists()


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_sync_no_data(tmp_path, mock_aioresponses):
    mock_aioresponses.get(
        PLANS_ENDPOINT_RE, body=json.dumps({"data": {"plans": PLANS}})
    )
    mock_aioresponses.get(
        ACCOUNTS_ENDPOINT_RE,
        body=json.dumps({"data": {"accounts": []}}),
        repeat=True,
    )
    mock_aioresponses.get(
        CATEGORIES_ENDPOINT_RE,
        body=json.dumps({"data": {"category_groups": []}}),
        repeat=True,
    )
    mock_aioresponses.get(
        PAYEES_ENDPOINT_RE, body=json.dumps({"data": {"payees": []}}), repeat=True
    )
    mock_aioresponses.get(
        TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps(
            {
                "data": {
                    "transactions": [],
                    "server_knowledge": SERVER_KNOWLEDGE_1,
                }
            }
        ),
        repeat=True,
    )
    mock_aioresponses.get(
        SCHEDULED_TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps({"data": {"scheduled_transactions": []}}),
        repeat=True,
    )

    # create the db and tables to exercise all code branches
    db = tmp_path / "db.sqlite"
    async with aiosqlite.connect(db) as con:
        await con.executescript(await contents("create-relations.sql"))

    await sync(TOKEN, db, False)


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_sync_no_data_quiet(tmp_path, mock_aioresponses, capsys):
    mock_aioresponses.get(
        PLANS_ENDPOINT_RE, body=json.dumps({"data": {"plans": PLANS}})
    )
    mock_aioresponses.get(
        ACCOUNTS_ENDPOINT_RE,
        body=json.dumps({"data": {"accounts": []}}),
        repeat=True,
    )
    mock_aioresponses.get(
        CATEGORIES_ENDPOINT_RE,
        body=json.dumps({"data": {"category_groups": []}}),
        repeat=True,
    )
    mock_aioresponses.get(
        PAYEES_ENDPOINT_RE, body=json.dumps({"data": {"payees": []}}), repeat=True
    )
    mock_aioresponses.get(
        TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps(
            {
                "data": {
                    "transactions": [],
                    "server_knowledge": SERVER_KNOWLEDGE_1,
                }
            }
        ),
        repeat=True,
    )
    mock_aioresponses.get(
        SCHEDULED_TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps({"data": {"scheduled_transactions": []}}),
        repeat=True,
    )

    db = tmp_path / "db.sqlite"
    async with aiosqlite.connect(db) as con:
        await con.executescript(await contents("create-relations.sql"))

    await sync(TOKEN, db, False, quiet=True)

    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_sync(tmp_path, mock_aioresponses):
    mock_aioresponses.get(
        PLANS_ENDPOINT_RE, body=json.dumps({"data": {"plans": PLANS}})
    )
    mock_aioresponses.get(
        ACCOUNTS_ENDPOINT_RE,
        body=json.dumps({"data": {"accounts": ACCOUNTS}}),
        repeat=True,
    )
    mock_aioresponses.get(
        CATEGORIES_ENDPOINT_RE,
        body=json.dumps({"data": {"category_groups": CATEGORY_GROUPS}}),
        repeat=True,
    )
    mock_aioresponses.get(
        PAYEES_ENDPOINT_RE, body=json.dumps({"data": {"payees": PAYEES}}), repeat=True
    )
    mock_aioresponses.get(
        TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps(
            {
                "data": {
                    "transactions": TRANSACTIONS,
                    "server_knowledge": SERVER_KNOWLEDGE_1,
                }
            }
        ),
        repeat=True,
    )
    mock_aioresponses.get(
        SCHEDULED_TRANSACTIONS_ENDPOINT_RE,
        body=json.dumps({"data": {"scheduled_transactions": SCHEDULED_TRANSACTIONS}}),
        repeat=True,
    )

    await sync(TOKEN, tmp_path / "db.sqlite", True)
