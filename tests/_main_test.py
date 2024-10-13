from __future__ import annotations

from pathlib import Path

import pytest

from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab._main import get_last_knowledge_of_server
from sqlite_export_for_ynab._main import insert_accounts
from sqlite_export_for_ynab._main import insert_budgets
from sqlite_export_for_ynab._main import insert_category_groups
from testing.fixtures import ACCOUNT_ID_1
from testing.fixtures import ACCOUNT_ID_2
from testing.fixtures import ACCOUNTS
from testing.fixtures import BUDGET_ID_1
from testing.fixtures import BUDGET_ID_2
from testing.fixtures import BUDGETS
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
from testing.fixtures import LKOS
from testing.fixtures import strip_nones


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
    insert_accounts(cur, BUDGET_ID_1, ACCOUNTS)
    cur.execute("SELECT * FROM accounts ORDER BY name")
    assert [strip_nones(d) for d in cur.fetchall()] == [
        {
            "id": ACCOUNT_ID_1,
            "name": ACCOUNTS[0]["name"],
            "TYPE": ACCOUNTS[0]["type"],
            "budget_id": BUDGET_ID_1,
        },
        {
            "id": ACCOUNT_ID_2,
            "name": ACCOUNTS[1]["name"],
            "TYPE": ACCOUNTS[1]["type"],
            "budget_id": BUDGET_ID_1,
        },
    ]
    cur.execute("SELECT * FROM account_periodic_values ORDER BY name")
    assert cur.fetchall() == [
        {
            "account_id": ACCOUNT_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": "debt_escrow_amounts",
            "DATE": "2024-01-01",
            "amount": 160000,
        },
        {
            "account_id": ACCOUNT_ID_1,
            "budget_id": BUDGET_ID_1,
            "name": "debt_interest_rates",
            "DATE": "2024-02-01",
            "amount": 5000,
        },
    ]


@pytest.mark.usefixtures(cur.__name__)
def test_insert_category_groups(cur):
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
