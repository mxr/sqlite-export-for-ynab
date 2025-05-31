from __future__ import annotations

import re
import sqlite3
from typing import Any
from uuid import uuid4

import pytest
from aioresponses import aioresponses

from sqlite_export_for_ynab._main import _row_factory
from sqlite_export_for_ynab._main import contents

BUDGET_ID_1 = str(uuid4())
BUDGET_ID_2 = str(uuid4())

BUDGETS: list[dict[str, Any]] = [
    {
        "id": BUDGET_ID_1,
        "name": "Budget 1",
    },
    {
        "id": BUDGET_ID_2,
        "name": "Budget 2",
    },
]

SERVER_KNOWLEDGE_1 = 107667
SERVER_KNOWLEDGE_2 = 107668

LKOS = {
    BUDGET_ID_1: SERVER_KNOWLEDGE_1,
    BUDGET_ID_2: SERVER_KNOWLEDGE_2,
}

ACCOUNT_ID_1 = str(uuid4())
ACCOUNT_ID_2 = str(uuid4())

ACCOUNTS: list[dict[str, Any]] = [
    {
        "id": ACCOUNT_ID_1,
        "name": "Account 1",
        "type": "checking",
        "debt_escrow_amounts": {
            "2024-01-01": 160000,
        },
        "debt_interest_rates": {
            "2024-02-01": 5000,
        },
        "debt_minimum_payments": {},
    },
    {
        "id": ACCOUNT_ID_2,
        "name": "Account 2",
        "type": "savings",
        "debt_escrow_amounts": {},
        "debt_interest_rates": {},
        "debt_minimum_payments": {},
    },
]

CATEGORY_GROUP_ID_1 = str(uuid4())
CATEGORY_GROUP_ID_2 = str(uuid4())

CATEGORY_ID_1 = str(uuid4())
CATEGORY_ID_2 = str(uuid4())
CATEGORY_ID_3 = str(uuid4())
CATEGORY_ID_4 = str(uuid4())

CATEGORY_NAME_1 = "Category 1"
CATEGORY_NAME_2 = "Category 2"
CATEGORY_NAME_3 = "Category 3"
CATEGORY_NAME_4 = "Category 4"

CATEGORY_GROUPS: list[dict[str, Any]] = [
    {
        "id": CATEGORY_GROUP_ID_1,
        "name": "Category Group 1",
        "categories": [
            {
                "id": CATEGORY_ID_1,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "name": CATEGORY_NAME_1,
            },
            {
                "id": CATEGORY_ID_2,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "name": CATEGORY_NAME_2,
            },
        ],
    },
    {
        "id": CATEGORY_GROUP_ID_2,
        "name": "Category Group 2",
        "categories": [
            {
                "id": CATEGORY_ID_3,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "name": CATEGORY_NAME_3,
            },
            {
                "id": CATEGORY_ID_4,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "name": CATEGORY_NAME_4,
            },
        ],
    },
]

PAYEE_ID_1 = str(uuid4())
PAYEE_ID_2 = str(uuid4())

PAYEES: list[dict[str, Any]] = [
    {
        "id": PAYEE_ID_1,
        "name": "Payee 1",
    },
    {
        "id": PAYEE_ID_2,
        "name": "Payee 2",
    },
]

TRANSACTION_ID_1 = str(uuid4())
TRANSACTION_ID_2 = str(uuid4())

SUBTRANSACTION_ID_1 = str(uuid4())
SUBTRANSACTION_ID_2 = str(uuid4())

TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": TRANSACTION_ID_1,
        "date": "2024-01-01",
        "amount": -10000,
        "deleted": False,
        "subtransactions": [
            {
                "id": SUBTRANSACTION_ID_1,
                "transaction_id": TRANSACTION_ID_1,
                "amount": -7500,
                "deleted": False,
            },
            {
                "id": SUBTRANSACTION_ID_2,
                "transaction_id": TRANSACTION_ID_1,
                "amount": -2500,
                "deleted": False,
            },
        ],
    },
    {
        "id": TRANSACTION_ID_2,
        "date": "2024-02-01",
        "amount": -15000,
        "deleted": True,
        "subtransactions": [],
    },
]

SCHEDULED_TRANSACTION_ID_1 = str(uuid4())
SCHEDULED_TRANSACTION_ID_2 = str(uuid4())

SCHEDULED_SUBTRANSACTION_ID_1 = str(uuid4())
SCHEDULED_SUBTRANSACTION_ID_2 = str(uuid4())

SCHEDULED_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": SCHEDULED_TRANSACTION_ID_1,
        "amount": -12000,
        "deleted": False,
        "subtransactions": [
            {
                "id": SCHEDULED_SUBTRANSACTION_ID_1,
                "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "deleted": False,
                "amount": -8040,
            },
            {
                "id": SCHEDULED_SUBTRANSACTION_ID_2,
                "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "deleted": False,
                "amount": -2960,
            },
        ],
    },
    {
        "id": SCHEDULED_TRANSACTION_ID_2,
        "amount": -11000,
        "deleted": True,
        "subtransactions": [],
    },
]


@pytest.fixture
def cur():
    with sqlite3.connect(":memory:") as con:
        con.row_factory = _row_factory
        cursor = con.cursor()
        cursor.executescript(contents("create-relations.sql"))
        yield cursor


@pytest.fixture
def mock_aioresponses():
    with aioresponses() as m:
        yield m


def strip_nones(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


TOKEN = f"token-{uuid4()}"
EXAMPLE_ENDPOINT_RE = re.compile(".+/example$")
BUDGETS_ENDPOINT_RE = re.compile(".+/budgets$")
ACCOUNTS_ENDPOINT_RE = re.compile(".+/accounts$")
CATEGORIES_ENDPOINT_RE = re.compile(".+/categories$")
PAYEES_ENDPOINT_RE = re.compile(".+/payees$")
TRANSACTIONS_ENDPOINT_RE = re.compile(".+/transactions$")
SCHEDULED_TRANSACTIONS_ENDPOINT_RE = re.compile(".+/scheduled_transactions$")
