from __future__ import annotations

import asyncio
import json
import sqlite3
from configparser import ConfigParser
from pathlib import Path
from unittest.mock import patch

import aiohttp
import pytest
from aiohttp.http_exceptions import HttpProcessingError
from tqdm import tqdm

from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab._main import _ALL_RELATIONS
from sqlite_export_for_ynab._main import _ENV_TOKEN
from sqlite_export_for_ynab._main import _PACKAGE
from sqlite_export_for_ynab._main import contents
from sqlite_export_for_ynab._main import get_last_knowledge_of_server
from sqlite_export_for_ynab._main import get_relations
from sqlite_export_for_ynab._main import insert_accounts
from sqlite_export_for_ynab._main import insert_budgets
from sqlite_export_for_ynab._main import insert_category_groups
from sqlite_export_for_ynab._main import insert_payees
from sqlite_export_for_ynab._main import insert_scheduled_transactions
from sqlite_export_for_ynab._main import insert_transactions
from sqlite_export_for_ynab._main import main
from sqlite_export_for_ynab._main import ProgressYnabClient
from sqlite_export_for_ynab._main import sync
from sqlite_export_for_ynab._main import YnabClient
from testing.fixtures import ACCOUNT_ID_1
from testing.fixtures import ACCOUNT_ID_2
from testing.fixtures import ACCOUNTS
from testing.fixtures import ACCOUNTS_ENDPOINT_RE
from testing.fixtures import BUDGET_ID_1
from testing.fixtures import BUDGET_ID_2
from testing.fixtures import BUDGETS
from testing.fixtures import BUDGETS_ENDPOINT_RE
from testing.fixtures import CATEGORIES_ENDPOINT_RE
from testing.fixtures import CATEGORY_GROUP_ID_1
from testing.fixtures import CATEGORY_GROUP_ID_2
from testing.fixtures import CATEGORY_GROUPS
from testing.fixtures import CATEGORY_ID_1
from testing.fixtures import CATEGORY_ID_2
from testing.fixtures import CATEGORY_ID_3
from testing.fixtures import CATEGORY_ID_4
from testing.fixtures import CATEGORY_NAME_1
from testing.fixtures import CATEGORY_NAME_2
from testing.fixtures import CATEGORY_NAME_3
from testing.fixtures import CATEGORY_NAME_4
from testing.fixtures import cur
from testing.fixtures import EXAMPLE_ENDPOINT_RE
from testing.fixtures import LKOS
from testing.fixtures import mock_aioresponses
from testing.fixtures import PAYEE_ID_1
from testing.fixtures import PAYEE_ID_2
from testing.fixtures import PAYEES
from testing.fixtures import PAYEES_ENDPOINT_RE
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_1
from testing.fixtures import SCHEDULED_SUBTRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTION_ID_1
from testing.fixtures import SCHEDULED_TRANSACTION_ID_2
from testing.fixtures import SCHEDULED_TRANSACTIONS
from testing.fixtures import SCHEDULED_TRANSACTIONS_ENDPOINT_RE
from testing.fixtures import SERVER_KNOWLEDGE_1
from testing.fixtures import strip_nones
from testing.fixtures import SUBTRANSACTION_ID_1
from testing.fixtures import SUBTRANSACTION_ID_2
from testing.fixtures import TOKEN
from testing.fixtures import TRANSACTION_ID_1
from testing.fixtures import TRANSACTION_ID_2
from testing.fixtures import TRANSACTIONS
from testing.fixtures import TRANSACTIONS_ENDPOINT_RE


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


@pytest.mark.usefixtures(cur.__name__)
def test_get_relations(cur):
    assert get_relations(cur) == _ALL_RELATIONS


@pytest.mark.usefixtures(cur.__name__)
def test_get_last_knowledge_of_server(cur):
    insert_budgets(cur, BUDGETS, LKOS)
    assert get_last_knowledge_of_server(cur) == LKOS


@pytest.mark.usefixtures(cur.__name__)
def test_insert_budgets(cur):
    insert_budgets(cur, BUDGETS, LKOS)
    cur.execute("SELECT * FROM budgets ORDER BY name")
    assert cur.fetchall() == [
        {
            "id": BUDGET_ID_1,
            "name": BUDGETS[0]["name"],
            "last_knowledge_of_server": LKOS[BUDGET_ID_1],
        },
        {
            "id": BUDGET_ID_2,
            "name": BUDGETS[1]["name"],
            "last_knowledge_of_server": LKOS[BUDGET_ID_2],
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_accounts(cur):
    insert_accounts(cur, BUDGET_ID_1, [])
    assert not cur.execute("SELECT * FROM accounts").fetchall()
    assert not cur.execute("SELECT * FROM account_periodic_values").fetchall()

    insert_accounts(cur, BUDGET_ID_1, ACCOUNTS)
    cur.execute("SELECT * FROM accounts ORDER BY name")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": ACCOUNT_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": ACCOUNTS[0]["name"],
            "type": ACCOUNTS[0]["type"],
        },
        {
            "id": ACCOUNT_ID_2,
            "budget_id": BUDGET_ID_1,
            "name": ACCOUNTS[1]["name"],
            "type": ACCOUNTS[1]["type"],
        },
    ]

    cur.execute("SELECT * FROM account_periodic_values ORDER BY name")
    assert cur.fetchall() == [
        {
            "account_id": ACCOUNT_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": "debt_escrow_amounts",
            "date": "2024-01-01",
            "amount": 160000,
        },
        {
            "account_id": ACCOUNT_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": "debt_interest_rates",
            "date": "2024-02-01",
            "amount": 5000,
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_category_groups(cur):
    insert_category_groups(cur, BUDGET_ID_1, [])
    assert not cur.execute("SELECT * FROM category_groups").fetchall()
    assert not cur.execute("SELECT * FROM categories").fetchall()

    insert_category_groups(cur, BUDGET_ID_1, CATEGORY_GROUPS)
    cur.execute("SELECT * FROM category_groups ORDER BY name")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": CATEGORY_GROUP_ID_1,
            "name": CATEGORY_GROUPS[0]["name"],
            "budget_id": BUDGET_ID_1,
        },
        {
            "id": CATEGORY_GROUP_ID_2,
            "name": CATEGORY_GROUPS[1]["name"],
            "budget_id": BUDGET_ID_1,
        },
    ]

    cur.execute("SELECT * FROM categories ORDER BY name")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": CATEGORY_ID_1,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": CATEGORY_NAME_1,
        },
        {
            "id": CATEGORY_ID_2,
            "category_group_id": CATEGORY_GROUP_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": CATEGORY_NAME_2,
        },
        {
            "id": CATEGORY_ID_3,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "budget_id": BUDGET_ID_1,
            "name": CATEGORY_NAME_3,
        },
        {
            "id": CATEGORY_ID_4,
            "category_group_id": CATEGORY_GROUP_ID_2,
            "budget_id": BUDGET_ID_1,
            "name": CATEGORY_NAME_4,
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_payees(cur):
    insert_payees(cur, BUDGET_ID_1, [])
    assert not cur.execute("SELECT * FROM payees").fetchall()

    insert_payees(cur, BUDGET_ID_1, PAYEES)
    cur.execute("SELECT * FROM payees ORDER BY name")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": PAYEE_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": PAYEES[0]["name"],
        },
        {
            "id": PAYEE_ID_2,
            "budget_id": BUDGET_ID_1,
            "name": PAYEES[1]["name"],
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_transactions(cur):
    insert_transactions(cur, BUDGET_ID_1, [])
    assert not cur.execute("SELECT * FROM transactions").fetchall()
    assert not cur.execute("SELECT * FROM subtransactions").fetchall()

    insert_transactions(cur, BUDGET_ID_1, TRANSACTIONS)
    cur.execute("SELECT * FROM transactions ORDER BY date")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "date": "2024-01-01",
            "amount": -10000,
            "deleted": False,
        },
        {
            "id": TRANSACTION_ID_2,
            "budget_id": BUDGET_ID_1,
            "date": "2024-02-01",
            "amount": -15000,
            "deleted": True,
        },
    ]

    cur.execute("SELECT * FROM subtransactions ORDER BY amount")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": SUBTRANSACTION_ID_1,
            "transaction_id": TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "amount": -7500,
            "deleted": False,
        },
        {
            "id": SUBTRANSACTION_ID_2,
            "transaction_id": TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "amount": -2500,
            "deleted": False,
        },
    ]

    cur.execute("SELECT * FROM flat_transactions ORDER BY amount")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "transaction_id": TRANSACTION_ID_1,
            "subtransaction_id": SUBTRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "date": "2024-01-01",
            "id": SUBTRANSACTION_ID_1,
            "amount": -7500,
            "amount_major": pytest.approx(7.50),
        },
        {
            "transaction_id": TRANSACTION_ID_1,
            "subtransaction_id": SUBTRANSACTION_ID_2,
            "budget_id": BUDGET_ID_1,
            "date": "2024-01-01",
            "id": SUBTRANSACTION_ID_2,
            "amount": -2500,
            "amount_major": pytest.approx(2.50),
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_scheduled_transactions(cur):
    insert_scheduled_transactions(cur, BUDGET_ID_1, [])
    assert not cur.execute("SELECT * FROM scheduled_transactions").fetchall()
    assert not cur.execute("SELECT * FROM scheduled_subtransactions").fetchall()

    insert_scheduled_transactions(cur, BUDGET_ID_1, SCHEDULED_TRANSACTIONS)
    cur.execute("SELECT * FROM scheduled_transactions ORDER BY amount")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": SCHEDULED_TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "amount": -12000,
            "deleted": False,
        },
        {
            "id": SCHEDULED_TRANSACTION_ID_2,
            "budget_id": BUDGET_ID_1,
            "amount": -11000,
            "deleted": True,
        },
    ]

    cur.execute("SELECT * FROM scheduled_subtransactions ORDER BY amount")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": SCHEDULED_SUBTRANSACTION_ID_1,
            "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "amount": -8040,
            "deleted": False,
        },
        {
            "id": SCHEDULED_SUBTRANSACTION_ID_2,
            "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "amount": -2960,
            "deleted": False,
        },
    ]

    cur.execute("SELECT * FROM scheduled_flat_transactions ORDER BY amount")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_1,
            "budget_id": BUDGET_ID_1,
            "id": SCHEDULED_SUBTRANSACTION_ID_1,
            "amount": -8040,
            "amount_major": pytest.approx(8.04),
        },
        {
            "transaction_id": SCHEDULED_TRANSACTION_ID_1,
            "subtransaction_id": SCHEDULED_SUBTRANSACTION_ID_2,
            "budget_id": BUDGET_ID_1,
            "id": SCHEDULED_SUBTRANSACTION_ID_2,
            "amount": -2960,
            "amount_major": pytest.approx(2.96),
        },
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_progress_ynab_client_ok(mock_aioresponses):
    expected = {"example": [{"id": 1, "value": 2}, {"id": 3, "value": 4}]}
    mock_aioresponses.get(EXAMPLE_ENDPOINT_RE, body=json.dumps({"data": expected}))

    with tqdm(disable=True) as pbar:
        async with aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session:
            pyc = ProgressYnabClient(YnabClient(TOKEN, session), pbar)
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
    sync.assert_called()
    assert ret == 0


def test_main_no_token(tmp_path, monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError):
        main(("--db", str(tmp_path / "db.sqlite")))


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_sync_no_data(tmp_path, mock_aioresponses):
    mock_aioresponses.get(
        BUDGETS_ENDPOINT_RE, body=json.dumps({"data": {"budgets": BUDGETS}})
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
    with sqlite3.connect(db) as con:
        con.executescript(contents("create-relations.sql"))

    await sync(TOKEN, db, False)


@pytest.mark.asyncio
@pytest.mark.usefixtures(mock_aioresponses.__name__)
async def test_sync(tmp_path, mock_aioresponses):
    mock_aioresponses.get(
        BUDGETS_ENDPOINT_RE, body=json.dumps({"data": {"budgets": BUDGETS}})
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
