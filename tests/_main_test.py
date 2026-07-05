from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import aiosqlite
import fasteners
import pytest
import pytest_asyncio
from rich.progress import Progress

from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab._main import _ALL_RELATIONS
from sqlite_export_for_ynab._main import _Context
from sqlite_export_for_ynab._main import _context
from sqlite_export_for_ynab._main import _ENV_TOKEN
from sqlite_export_for_ynab._main import _get_plan_summaries
from sqlite_export_for_ynab._main import _PACKAGE
from sqlite_export_for_ynab._main import _PROGRESS_COLUMNS
from sqlite_export_for_ynab._main import _ProgressYnab
from sqlite_export_for_ynab._main import async_main
from sqlite_export_for_ynab._main import asyncio_for_ynab
from sqlite_export_for_ynab._main import contents
from sqlite_export_for_ynab._main import get_last_knowledge_of_server
from sqlite_export_for_ynab._main import get_relations
from sqlite_export_for_ynab._main import insert_accounts
from sqlite_export_for_ynab._main import insert_category_groups
from sqlite_export_for_ynab._main import insert_entries
from sqlite_export_for_ynab._main import insert_payees
from sqlite_export_for_ynab._main import insert_plans
from sqlite_export_for_ynab._main import insert_scheduled_transactions
from sqlite_export_for_ynab._main import insert_transactions
from sqlite_export_for_ynab._main import main
from sqlite_export_for_ynab._main import resolve_token
from sqlite_export_for_ynab._main import sync
from testing.fixtures import ACCOUNT_ID_1
from testing.fixtures import ACCOUNT_ID_2
from testing.fixtures import ACCOUNTS
from testing.fixtures import accounts_response
from testing.fixtures import categories_response
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
from testing.fixtures import LKOS
from testing.fixtures import PAYEE_ID_1
from testing.fixtures import PAYEE_ID_2
from testing.fixtures import PAYEES
from testing.fixtures import payees_response
from testing.fixtures import PLAN_ID_1
from testing.fixtures import PLAN_ID_2
from testing.fixtures import plan_response
from testing.fixtures import PLANS
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_1
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTION_ID_1
from testing.fixtures import SCHEDULED_TRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTION_ID_3
from testing.fixtures import SCHEDULED_TRANSACTIONS
from testing.fixtures import scheduled_transactions_response
from testing.fixtures import SERVER_KNOWLEDGE_1
from testing.fixtures import SERVER_KNOWLEDGE_2
from testing.fixtures import SUBTRANSACTION_ID_1
from testing.fixtures import SUBTRANSACTION_ID_2
from testing.fixtures import TOKEN
from testing.fixtures import TRANSACTION_ID_1
from testing.fixtures import TRANSACTION_ID_2
from testing.fixtures import TRANSACTION_ID_3
from testing.fixtures import TRANSACTIONS
from testing.fixtures import transactions_response


async def fetchall(con, query):
    async with con.cursor() as cur:
        await cur.execute(query)
        return await cur.fetchall()


def assert_rows(rows, expected_rows):
    assert len(rows) == len(expected_rows)
    for row, expected in zip(rows, expected_rows, strict=True):
        actual = dict(row)
        assert {k: actual[k] for k in expected} == expected


@pytest_asyncio.fixture
async def context(tmp_path):
    with Progress(*_PROGRESS_COLUMNS, disable=True) as progress:
        async with aiosqlite.connect(":memory:") as con:
            con.row_factory = aiosqlite.Row
            await con.executescript(await contents("create-relations.sql"))
            lock = fasteners.InterProcessLock(
                tmp_path / "sqlite-export-for-ynab-test.lock"
            )
            yield _Context(progress, con, lock, Mock(spec=asyncio_for_ynab.ApiClient))


@pytest.mark.asyncio
async def test_progress_ynab_get_transactions_uses_last_knowledge_of_server_when_present(
    context,
):
    task_id = context.progress.add_task("Plan Data", total=1)
    py = _ProgressYnab(context, PLAN_ID_1, LKOS, task_id)

    with patch(
        "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
        new=AsyncMock(
            return_value=transactions_response(TRANSACTIONS, SERVER_KNOWLEDGE_1)
        ),
    ) as get_transactions:
        response = await py.get_transactions(date(2020, 1, 1))

    get_transactions.assert_awaited_once_with(
        plan_id=PLAN_ID_1, last_knowledge_of_server=LKOS[PLAN_ID_1]
    )
    assert response.data.transactions == TRANSACTIONS


@pytest.mark.asyncio
async def test_progress_ynab_get_transactions_uses_single_call_when_no_first_month(
    context,
):
    task_id = context.progress.add_task("Plan Data", total=1)
    py = _ProgressYnab(context, PLAN_ID_1, {}, task_id)

    with patch(
        "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
        new=AsyncMock(
            return_value=transactions_response(TRANSACTIONS, SERVER_KNOWLEDGE_1)
        ),
    ) as get_transactions:
        response = await py.get_transactions(None)

    get_transactions.assert_awaited_once_with(
        plan_id=PLAN_ID_1, last_knowledge_of_server=None
    )
    assert response.data.transactions == TRANSACTIONS


@pytest.mark.asyncio
async def test_progress_ynab_get_transactions_chunks_by_year_when_full_refresh(context):
    task_id = context.progress.add_task("Plan Data", total=1)
    py = _ProgressYnab(context, PLAN_ID_1, {}, task_id)

    current_year = date.today().year
    old_transaction, new_transaction, _ = TRANSACTIONS

    def side_effect(*, plan_id, since_date, until_date):
        assert plan_id == PLAN_ID_1
        assert since_date == date(since_date.year, 1, 1)
        assert until_date == date(since_date.year, 12, 31)
        if since_date.year == current_year - 1:
            return transactions_response([old_transaction], SERVER_KNOWLEDGE_1)
        return transactions_response([new_transaction], SERVER_KNOWLEDGE_2)

    with patch(
        "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
        new=AsyncMock(side_effect=side_effect),
    ):
        response = await py.get_transactions(date(current_year - 1, 6, 1))

    assert {t.id for t in response.data.transactions} == {
        old_transaction.id,
        new_transaction.id,
    }
    assert response.data.server_knowledge == SERVER_KNOWLEDGE_2


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
    assert_rows(
        await fetchall(context.con, "SELECT * FROM plans ORDER BY name"),
        [
            {
                "id": PLAN_ID_1,
                "name": PLANS[0].name,
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
                "name": PLANS[1].name,
                "currency_format_currency_symbol": "$",
                "currency_format_decimal_digits": 2,
                "currency_format_decimal_separator": ".",
                "currency_format_display_symbol": 1,
                "currency_format_group_separator": ",",
                "currency_format_iso_code": "USD",
                "currency_format_symbol_first": 1,
                "last_knowledge_of_server": LKOS[PLAN_ID_2],
            },
        ],
    )


@pytest.mark.asyncio
async def test_insert_accounts(context):
    await insert_accounts(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM accounts")
    assert not await fetchall(context.con, "SELECT * FROM account_periodic_values")

    await insert_accounts(context, PLAN_ID_1, ACCOUNTS)
    assert_rows(
        await fetchall(context.con, "SELECT * FROM accounts ORDER BY name"),
        [
            {
                "id": ACCOUNT_ID_1,
                "plan_id": PLAN_ID_1,
                "name": ACCOUNTS[0].name,
                "type": ACCOUNTS[0].type,
                "balance": 160000,
                "balance_formatted": "$160.00",
                "balance_currency": 160.0,
                "cleared_balance": 120000,
                "cleared_balance_formatted": "$120.00",
                "cleared_balance_currency": 120.0,
                "closed": False,
                "deleted": False,
                "on_budget": True,
                "transfer_payee_id": PAYEE_ID_1,
                "uncleared_balance": 40000,
                "uncleared_balance_formatted": "$40.00",
                "uncleared_balance_currency": 40.0,
            },
            {
                "id": ACCOUNT_ID_2,
                "plan_id": PLAN_ID_1,
                "name": ACCOUNTS[1].name,
                "type": ACCOUNTS[1].type,
                "balance": 25000,
                "balance_formatted": "$25.00",
                "balance_currency": 25.0,
                "cleared_balance": 25000,
                "cleared_balance_formatted": "$25.00",
                "cleared_balance_currency": 25.0,
                "closed": False,
                "deleted": False,
                "on_budget": True,
                "transfer_payee_id": PAYEE_ID_2,
                "uncleared_balance": 0,
                "uncleared_balance_formatted": "$0.00",
                "uncleared_balance_currency": 0.0,
            },
        ],
    )

    assert_rows(
        await fetchall(
            context.con, "SELECT * FROM account_periodic_values ORDER BY name"
        ),
        [
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
        ],
    )


@pytest.mark.asyncio
async def test_insert_category_groups(context):
    await insert_category_groups(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM category_groups")
    assert not await fetchall(context.con, "SELECT * FROM categories")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    assert_rows(
        await fetchall(context.con, "SELECT * FROM category_groups ORDER BY name"),
        [
            {
                "id": CATEGORY_GROUP_ID_1,
                "name": CATEGORY_GROUP_NAME_1,
                "plan_id": PLAN_ID_1,
                "hidden": False,
                "internal": False,
                "deleted": False,
            },
            {
                "id": CATEGORY_GROUP_ID_2,
                "name": CATEGORY_GROUP_NAME_2,
                "plan_id": PLAN_ID_1,
                "hidden": False,
                "internal": False,
                "deleted": False,
            },
        ],
    )

    assert_rows(
        await fetchall(context.con, "SELECT * FROM categories ORDER BY name"),
        [
            {
                "id": CATEGORY_ID_1,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "plan_id": PLAN_ID_1,
                "name": CATEGORY_NAME_1,
                "hidden": False,
                "internal": False,
                "original_category_group_id": None,
                "note": None,
                "budgeted": 14500,
                "balance_formatted": "$12.00",
                "balance_currency": 12.0,
                "activity": 2500,
                "activity_formatted": "$2.50",
                "activity_currency": 2.5,
                "goal_type": None,
                "goal_needs_whole_amount": None,
                "goal_day": None,
                "goal_cadence": None,
                "goal_cadence_frequency": None,
                "goal_creation_month": None,
                "goal_snoozed_at": None,
                "goal_target": 20000,
                "budgeted_formatted": "$14.50",
                "budgeted_currency": 14.5,
                "goal_target_formatted": "$20.00",
                "goal_target_currency": 20.0,
                "goal_target_date": CATEGORY_GOAL_TARGET_DATE_1,
                "goal_target_month": None,
                "goal_percentage_complete": None,
                "goal_months_to_budget": None,
                "goal_under_funded": 8000,
                "goal_under_funded_formatted": "$8.00",
                "goal_under_funded_currency": 8.0,
                "goal_overall_funded": 12000,
                "goal_overall_funded_formatted": "$12.00",
                "goal_overall_funded_currency": 12.0,
                "goal_overall_left": 8000,
                "goal_overall_left_formatted": "$8.00",
                "goal_overall_left_currency": 8.0,
                "deleted": False,
            },
            {
                "id": CATEGORY_ID_2,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "plan_id": PLAN_ID_1,
                "name": CATEGORY_NAME_2,
                "hidden": False,
                "internal": False,
                "original_category_group_id": None,
                "note": None,
                "budgeted": 10250,
                "balance_formatted": "$9.25",
                "balance_currency": 9.25,
                "activity": 1000,
                "activity_formatted": "$1.00",
                "activity_currency": 1.0,
                "goal_type": None,
                "goal_needs_whole_amount": None,
                "goal_day": None,
                "goal_cadence": None,
                "goal_cadence_frequency": None,
                "goal_creation_month": None,
                "goal_snoozed_at": None,
                "goal_target": None,
                "budgeted_formatted": "$10.25",
                "budgeted_currency": 10.25,
                "goal_target_formatted": None,
                "goal_target_currency": None,
                "goal_target_date": None,
                "goal_target_month": None,
                "goal_percentage_complete": None,
                "goal_months_to_budget": None,
                "goal_under_funded": None,
                "goal_under_funded_formatted": None,
                "goal_under_funded_currency": None,
                "goal_overall_funded": None,
                "goal_overall_funded_formatted": None,
                "goal_overall_funded_currency": None,
                "goal_overall_left": None,
                "goal_overall_left_formatted": None,
                "goal_overall_left_currency": None,
                "deleted": False,
            },
            {
                "id": CATEGORY_ID_3,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "category_group_name": CATEGORY_GROUP_NAME_2,
                "plan_id": PLAN_ID_1,
                "name": CATEGORY_NAME_3,
                "hidden": False,
                "internal": False,
                "original_category_group_id": None,
                "note": None,
                "budgeted": 15000,
                "balance_formatted": "$7.50",
                "balance_currency": 7.5,
                "activity": 7500,
                "activity_formatted": "$7.50",
                "activity_currency": 7.5,
                "goal_type": None,
                "goal_needs_whole_amount": None,
                "goal_day": None,
                "goal_cadence": None,
                "goal_cadence_frequency": None,
                "goal_creation_month": None,
                "goal_snoozed_at": None,
                "goal_target": None,
                "budgeted_formatted": "$15.00",
                "budgeted_currency": 15.0,
                "goal_target_formatted": None,
                "goal_target_currency": None,
                "goal_target_date": None,
                "goal_target_month": None,
                "goal_percentage_complete": None,
                "goal_months_to_budget": None,
                "goal_under_funded": None,
                "goal_under_funded_formatted": None,
                "goal_under_funded_currency": None,
                "goal_overall_funded": None,
                "goal_overall_funded_formatted": None,
                "goal_overall_funded_currency": None,
                "goal_overall_left": None,
                "goal_overall_left_formatted": None,
                "goal_overall_left_currency": None,
                "deleted": False,
            },
            {
                "id": CATEGORY_ID_4,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "category_group_name": CATEGORY_GROUP_NAME_2,
                "plan_id": PLAN_ID_1,
                "name": CATEGORY_NAME_4,
                "hidden": False,
                "internal": False,
                "original_category_group_id": None,
                "note": None,
                "budgeted": 20000,
                "balance_formatted": "$19.00",
                "balance_currency": 19.0,
                "activity": 19000,
                "activity_formatted": "$19.00",
                "activity_currency": 19.0,
                "goal_type": None,
                "goal_needs_whole_amount": None,
                "goal_day": None,
                "goal_cadence": None,
                "goal_cadence_frequency": None,
                "goal_creation_month": None,
                "goal_snoozed_at": None,
                "goal_target": None,
                "budgeted_formatted": "$20.00",
                "budgeted_currency": 20.0,
                "goal_target_formatted": None,
                "goal_target_currency": None,
                "goal_target_date": None,
                "goal_target_month": None,
                "goal_percentage_complete": None,
                "goal_months_to_budget": None,
                "goal_under_funded": None,
                "goal_under_funded_formatted": None,
                "goal_under_funded_currency": None,
                "goal_overall_funded": None,
                "goal_overall_funded_formatted": None,
                "goal_overall_funded_currency": None,
                "goal_overall_left": None,
                "goal_overall_left_formatted": None,
                "goal_overall_left_currency": None,
                "deleted": False,
            },
        ],
    )


@pytest.mark.asyncio
async def test_insert_category_group_without_categories(context):
    await insert_category_groups(
        context,
        PLAN_ID_1,
        [CATEGORY_GROUPS[0].model_copy(update={"categories": []})],
    )

    assert_rows(
        await fetchall(context.con, "SELECT * FROM category_groups ORDER BY name"),
        [
            {
                "id": CATEGORY_GROUP_ID_1,
                "name": CATEGORY_GROUP_NAME_1,
                "plan_id": PLAN_ID_1,
                "hidden": False,
                "internal": False,
                "deleted": False,
            },
        ],
    )
    assert not await fetchall(context.con, "SELECT * FROM categories")


@pytest.mark.asyncio
async def test_insert_payees(context):
    await insert_payees(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM payees")

    await insert_payees(context, PLAN_ID_1, PAYEES)
    assert_rows(
        await fetchall(context.con, "SELECT * FROM payees ORDER BY name"),
        [
            {
                "id": PAYEE_ID_1,
                "plan_id": PLAN_ID_1,
                "name": PAYEES[0].name,
                "transfer_account_id": None,
                "deleted": False,
            },
            {
                "id": PAYEE_ID_2,
                "plan_id": PLAN_ID_1,
                "name": PAYEES[1].name,
                "transfer_account_id": None,
                "deleted": False,
            },
        ],
    )


@pytest.mark.asyncio
async def test_insert_entries_ignores_unknown_keys(context):
    task_id = context.progress.add_task("Payees", total=1)
    entry = {
        "id": PAYEE_ID_1,
        "name": "Payee",
        "transfer_account_id": None,
        "deleted": False,
        "brand_new_api_field": "surprise",
    }
    await insert_entries(context, "payees", PLAN_ID_1, [entry], task_id)
    assert_rows(
        await fetchall(context.con, "SELECT * FROM payees"),
        [
            {
                "id": PAYEE_ID_1,
                "plan_id": PLAN_ID_1,
                "name": "Payee",
                "transfer_account_id": None,
                "deleted": False,
            }
        ],
    )


@pytest.mark.asyncio
async def test_insert_transactions(context):
    await insert_transactions(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM transactions")
    assert not await fetchall(context.con, "SELECT * FROM subtransactions")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    await insert_transactions(context, PLAN_ID_1, TRANSACTIONS)
    assert_rows(
        await fetchall(context.con, "SELECT * FROM transactions ORDER BY date"),
        [
            {
                "id": TRANSACTION_ID_1,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date": "2024-01-01",
                "amount": -10000,
                "amount_formatted": "$10.00",
                "amount_currency": 10.0,
                "approved": 1,
                "category_id": CATEGORY_ID_3,
                "category_name": CATEGORY_NAME_3,
                "cleared": "cleared",
                "deleted": False,
            },
            {
                "id": TRANSACTION_ID_2,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date": "2024-02-01",
                "amount": -15000,
                "amount_formatted": "$15.00",
                "amount_currency": 15.0,
                "approved": 1,
                "category_id": CATEGORY_ID_2,
                "category_name": CATEGORY_NAME_2,
                "cleared": "cleared",
                "deleted": True,
            },
            {
                "id": TRANSACTION_ID_3,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date": "2024-03-01",
                "amount": -19000,
                "amount_formatted": "$19.00",
                "amount_currency": 19.0,
                "approved": 0,
                "category_id": CATEGORY_ID_4,
                "category_name": CATEGORY_NAME_4,
                "cleared": "uncleared",
                "deleted": False,
            },
        ],
    )

    assert_rows(
        await fetchall(context.con, "SELECT * FROM subtransactions ORDER BY amount"),
        [
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
        ],
    )

    assert_rows(
        await fetchall(context.con, "SELECT * FROM flat_transactions ORDER BY amount"),
        [
            {
                "transaction_id": TRANSACTION_ID_1,
                "subtransaction_id": SUBTRANSACTION_ID_1,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "cleared": "cleared",
                "date": "2024-01-01",
                "debt_transaction_type": None,
                "id": SUBTRANSACTION_ID_1,
                "amount": -7500,
                "amount_formatted": "$7.50",
                "amount_currency": 7.5,
                "category_id": CATEGORY_ID_1,
                "category_name": CATEGORY_NAME_1,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "flag_color": None,
                "flag_name": None,
                "import_id": None,
                "import_payee_name": None,
                "import_payee_name_original": None,
                "matched_transaction_id": None,
                "memo": None,
                "payee_id": None,
                "payee_name": None,
                "transfer_account_id": None,
                "transfer_transaction_id": None,
            },
            {
                "transaction_id": TRANSACTION_ID_1,
                "subtransaction_id": SUBTRANSACTION_ID_2,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "cleared": "cleared",
                "date": "2024-01-01",
                "debt_transaction_type": None,
                "id": SUBTRANSACTION_ID_2,
                "amount": -2500,
                "amount_formatted": "$2.50",
                "amount_currency": 2.5,
                "category_id": CATEGORY_ID_2,
                "category_name": CATEGORY_NAME_2,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "flag_color": None,
                "flag_name": None,
                "import_id": None,
                "import_payee_name": None,
                "import_payee_name_original": None,
                "matched_transaction_id": None,
                "memo": None,
                "payee_id": None,
                "payee_name": None,
                "transfer_account_id": None,
                "transfer_transaction_id": None,
            },
        ],
    )


@pytest.mark.asyncio
async def test_insert_scheduled_transactions(context):
    await insert_scheduled_transactions(context, PLAN_ID_1, [])
    assert not await fetchall(context.con, "SELECT * FROM scheduled_transactions")
    assert not await fetchall(context.con, "SELECT * FROM scheduled_subtransactions")

    await insert_category_groups(context, PLAN_ID_1, CATEGORY_GROUPS)
    await insert_scheduled_transactions(context, PLAN_ID_1, SCHEDULED_TRANSACTIONS)
    assert_rows(
        await fetchall(
            context.con, "SELECT * FROM scheduled_transactions ORDER BY amount"
        ),
        [
            {
                "id": SCHEDULED_TRANSACTION_ID_1,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-01-01",
                "date_next": "2024-01-01",
                "frequency": "monthly",
                "amount": -12000,
                "amount_formatted": "$12.00",
                "amount_currency": 12.0,
                "category_id": CATEGORY_ID_1,
                "category_name": CATEGORY_NAME_1,
                "flag_color": None,
                "flag_name": None,
                "deleted": False,
            },
            {
                "id": SCHEDULED_TRANSACTION_ID_2,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-02-01",
                "date_next": "2024-02-01",
                "frequency": "yearly",
                "amount": -11000,
                "amount_formatted": "$11.00",
                "amount_currency": 11.0,
                "category_id": CATEGORY_ID_3,
                "category_name": CATEGORY_NAME_3,
                "flag_color": None,
                "flag_name": None,
                "deleted": True,
            },
            {
                "id": SCHEDULED_TRANSACTION_ID_3,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-03-01",
                "date_next": "2024-03-01",
                "frequency": "everyOtherMonth",
                "amount": -9000,
                "amount_formatted": "$9.00",
                "amount_currency": 9.0,
                "category_id": CATEGORY_ID_4,
                "category_name": CATEGORY_NAME_4,
                "flag_color": None,
                "flag_name": None,
                "deleted": False,
            },
        ],
    )

    assert_rows(
        await fetchall(
            context.con, "SELECT * FROM scheduled_subtransactions ORDER BY amount"
        ),
        [
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
        ],
    )

    assert_rows(
        await fetchall(
            context.con, "SELECT * FROM scheduled_flat_transactions ORDER BY amount"
        ),
        [
            {
                "transaction_id": SCHEDULED_TRANSACTION_ID_3,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-03-01",
                "date_next": "2024-03-01",
                "id": SCHEDULED_TRANSACTION_ID_3,
                "frequency": "everyOtherMonth",
                "amount": -9000,
                "amount_formatted": "$9.00",
                "amount_currency": 9.0,
                "category_id": CATEGORY_ID_4,
                "category_name": CATEGORY_NAME_4,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "category_group_name": CATEGORY_GROUP_NAME_2,
                "flag_color": None,
                "flag_name": None,
                "memo": None,
                "payee_name": None,
                "payee_id": None,
                "transfer_account_id": None,
            },
            {
                "transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_1,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-01-01",
                "date_next": "2024-01-01",
                "id": SCHEDULED_SUBTRANSACTION_ID_1,
                "frequency": "monthly",
                "amount": -8040,
                "amount_formatted": "$8.04",
                "amount_currency": 8.04,
                "category_id": CATEGORY_ID_2,
                "category_name": CATEGORY_NAME_2,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "flag_color": None,
                "flag_name": None,
                "memo": None,
                "payee_name": None,
                "payee_id": None,
                "transfer_account_id": None,
            },
            {
                "transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_2,
                "plan_id": PLAN_ID_1,
                "account_id": ACCOUNT_ID_1,
                "account_name": "Account 1",
                "date_first": "2024-01-01",
                "date_next": "2024-01-01",
                "id": SCHEDULED_SUBTRANSACTION_ID_2,
                "frequency": "monthly",
                "amount": -2960,
                "amount_formatted": "$2.96",
                "amount_currency": 2.96,
                "category_id": CATEGORY_ID_3,
                "category_name": CATEGORY_NAME_3,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "category_group_name": CATEGORY_GROUP_NAME_2,
                "flag_color": None,
                "flag_name": None,
                "memo": None,
                "payee_name": None,
                "payee_id": None,
                "transfer_account_id": None,
            },
        ],
    )


@patch(
    "sqlite_export_for_ynab._main.PlansApi.get_plans",
    new=AsyncMock(side_effect=[RuntimeError("boom"), plan_response(PLANS)]),
)
@pytest.mark.asyncio
async def test_get_plan_summaries_retries():
    assert await _get_plan_summaries(Mock(spec=asyncio_for_ynab.ApiClient)) == PLANS


@patch("sqlite_export_for_ynab._main.sync")
@pytest.mark.asyncio
async def test_async_main_parses_full_refresh_and_quiet(sync, tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, TOKEN)

    ret = await async_main(
        ("--db", str(tmp_path / "db.sqlite"), "--full-refresh", "--quiet")
    )

    sync.assert_called_once_with(TOKEN, tmp_path / "db.sqlite", True, quiet=True)
    assert ret == 0


def test_main_version(capsys):
    with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    expected_version = data["project"]["version"]

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
)
@patch("sqlite_export_for_ynab._main.asyncio.get_running_loop")
@pytest.mark.asyncio
async def test_sync_lock_times_out(mock_get_running_loop, mock_acquire, tmp_path):
    class FakeLoop:
        def __init__(self):
            self._times = iter((0.0, 0.2))

        def time(self):
            return next(self._times)

    mock_get_running_loop.return_value = FakeLoop()
    mock_acquire.return_value = False

    with pytest.raises(TimeoutError):
        await _context(
            tmp_path / "db.sqlite",
            asyncio_for_ynab.Configuration(access_token=TOKEN),
            quiet=True,
            timeout=0.1,
        ).__aenter__()

    assert mock_acquire.call_count == 1
    assert mock_acquire.call_args.args[1] is False


@patch(
    "sqlite_export_for_ynab._main.fasteners.InterProcessLock.acquire",
    autospec=True,
)
@patch("sqlite_export_for_ynab._main.fasteners.InterProcessLock.release", autospec=True)
@patch("sqlite_export_for_ynab._main.asyncio.sleep")
@patch("sqlite_export_for_ynab._main.asyncio.get_running_loop")
@pytest.mark.asyncio
async def test_context_retries_after_sleep(
    mock_get_running_loop,
    mock_sleep,
    mock_release,
    mock_acquire,
    tmp_path,
):
    class FakeLoop:
        def __init__(self):
            self._times = iter((0.0, 0.0, 0.2))

        def time(self):
            return next(self._times)

    mock_get_running_loop.return_value = FakeLoop()
    mock_acquire.side_effect = [False, True]

    async with _context(
        tmp_path / "db.sqlite",
        asyncio_for_ynab.Configuration(access_token=TOKEN),
        quiet=True,
        timeout=0.1,
    ):
        pass

    assert mock_acquire.call_count == 2
    assert mock_acquire.call_args_list[0].args[1] is False
    assert mock_sleep.call_count == 1
    assert mock_release.call_count == 1


@pytest.mark.asyncio
async def test_context_removes_lock_file(tmp_path):
    db = tmp_path / "db.sqlite"
    lock_path = tmp_path / "db.sqlite.lock"

    async with _context(
        db, asyncio_for_ynab.Configuration(access_token=TOKEN), quiet=True
    ):
        assert lock_path.exists()

    assert not lock_path.exists()


@patch(
    "sqlite_export_for_ynab._main.PlansApi.get_plans",
    new=AsyncMock(return_value=plan_response(PLANS)),
)
@patch(
    "sqlite_export_for_ynab._main.AccountsApi.get_accounts",
    new=AsyncMock(return_value=accounts_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.CategoriesApi.get_categories",
    new=AsyncMock(return_value=categories_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.PayeesApi.get_payees",
    new=AsyncMock(return_value=payees_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
    new=AsyncMock(return_value=transactions_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.ScheduledTransactionsApi.get_scheduled_transactions",
    new=AsyncMock(return_value=scheduled_transactions_response([], SERVER_KNOWLEDGE_1)),
)
@pytest.mark.asyncio
async def test_sync_no_data(tmp_path):
    # create the db and tables to exercise all code branches
    db = tmp_path / "db.sqlite"
    async with aiosqlite.connect(db) as con:
        await con.executescript(await contents("create-relations.sql"))

    await sync(TOKEN, db, False)


@patch(
    "sqlite_export_for_ynab._main.PlansApi.get_plans",
    new=AsyncMock(return_value=plan_response(PLANS)),
)
@patch(
    "sqlite_export_for_ynab._main.AccountsApi.get_accounts",
    new=AsyncMock(return_value=accounts_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.CategoriesApi.get_categories",
    new=AsyncMock(return_value=categories_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.PayeesApi.get_payees",
    new=AsyncMock(return_value=payees_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
    new=AsyncMock(return_value=transactions_response([], SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.ScheduledTransactionsApi.get_scheduled_transactions",
    new=AsyncMock(return_value=scheduled_transactions_response([], SERVER_KNOWLEDGE_1)),
)
@pytest.mark.asyncio
async def test_sync_no_data_quiet(tmp_path, capsys):
    db = tmp_path / "db.sqlite"
    async with aiosqlite.connect(db) as con:
        await con.executescript(await contents("create-relations.sql"))

    await sync(TOKEN, db, False, quiet=True)

    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


@patch(
    "sqlite_export_for_ynab._main.PlansApi.get_plans",
    new=AsyncMock(return_value=plan_response(PLANS)),
)
@patch(
    "sqlite_export_for_ynab._main.AccountsApi.get_accounts",
    new=AsyncMock(return_value=accounts_response(ACCOUNTS, SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.CategoriesApi.get_categories",
    new=AsyncMock(
        return_value=categories_response(CATEGORY_GROUPS, SERVER_KNOWLEDGE_1)
    ),
)
@patch(
    "sqlite_export_for_ynab._main.PayeesApi.get_payees",
    new=AsyncMock(return_value=payees_response(PAYEES, SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.TransactionsApi.get_transactions",
    new=AsyncMock(return_value=transactions_response(TRANSACTIONS, SERVER_KNOWLEDGE_1)),
)
@patch(
    "sqlite_export_for_ynab._main.ScheduledTransactionsApi.get_scheduled_transactions",
    new=AsyncMock(
        return_value=scheduled_transactions_response(
            SCHEDULED_TRANSACTIONS,
            SERVER_KNOWLEDGE_1,
        )
    ),
)
@pytest.mark.asyncio
async def test_sync(tmp_path):
    await sync(TOKEN, tmp_path / "db.sqlite", True)
