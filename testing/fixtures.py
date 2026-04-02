from __future__ import annotations

import re
import sqlite3
from typing import Any
from uuid import uuid4

import pytest
from aioresponses import aioresponses

from sqlite_export_for_ynab._main import _row_factory
from sqlite_export_for_ynab._main import contents

PLAN_ID_1 = str(uuid4())
PLAN_ID_2 = str(uuid4())

PLANS: list[dict[str, Any]] = [
    {
        "id": PLAN_ID_1,
        "name": "Plan 1",
        "currency_format": {
            "currency_symbol": "$",
            "decimal_digits": 2,
            "decimal_separator": ".",
            "display_symbol": True,
            "example_format": "123,456.78",
            "group_separator": ",",
            "iso_code": "USD",
            "symbol_first": True,
        },
    },
    {
        "id": PLAN_ID_2,
        "name": "Plan 2",
        "currency_format": {
            "currency_symbol": "$",
            "decimal_digits": 2,
            "decimal_separator": ".",
            "display_symbol": True,
            "example_format": "123,456.78",
            "group_separator": ",",
            "iso_code": "USD",
            "symbol_first": True,
        },
    },
]

SERVER_KNOWLEDGE_1 = 107667
SERVER_KNOWLEDGE_2 = 107668

LKOS = {
    PLAN_ID_1: SERVER_KNOWLEDGE_1,
    PLAN_ID_2: SERVER_KNOWLEDGE_2,
}

ACCOUNT_ID_1 = str(uuid4())
ACCOUNT_ID_2 = str(uuid4())

ACCOUNTS: list[dict[str, Any]] = [
    {
        "id": ACCOUNT_ID_1,
        "name": "Account 1",
        "type": "checking",
        "balance_formatted": "$160.00",
        "balance_currency": 160.0,
        "cleared_balance_formatted": "$120.00",
        "cleared_balance_currency": 120.0,
        "uncleared_balance_formatted": "$40.00",
        "uncleared_balance_currency": 40.0,
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
        "balance_formatted": "$25.00",
        "balance_currency": 25.0,
        "cleared_balance_formatted": "$25.00",
        "cleared_balance_currency": 25.0,
        "uncleared_balance_formatted": "$0.00",
        "uncleared_balance_currency": 0.0,
        "debt_escrow_amounts": {},
        "debt_interest_rates": {},
        "debt_minimum_payments": {},
    },
]

CATEGORY_GROUP_ID_1 = str(uuid4())
CATEGORY_GROUP_ID_2 = str(uuid4())

CATEGORY_GROUP_NAME_1 = "Category Group 1"
CATEGORY_GROUP_NAME_2 = "Category Group 2"

CATEGORY_ID_1 = str(uuid4())
CATEGORY_ID_2 = str(uuid4())
CATEGORY_ID_3 = str(uuid4())
CATEGORY_ID_4 = str(uuid4())

CATEGORY_NAME_1 = "Category 1"
CATEGORY_NAME_2 = "Category 2"
CATEGORY_NAME_3 = "Category 3"
CATEGORY_NAME_4 = "Category 4"
CATEGORY_GOAL_TARGET_DATE_1 = "2026-12-31"

CATEGORY_GROUPS: list[dict[str, Any]] = [
    {
        "id": CATEGORY_GROUP_ID_1,
        "name": CATEGORY_GROUP_NAME_1,
        "categories": [
            {
                "id": CATEGORY_ID_1,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "name": CATEGORY_NAME_1,
                "balance_formatted": "$12.00",
                "balance_currency": 12.0,
                "activity_formatted": "$2.50",
                "activity_currency": 2.5,
                "budgeted_formatted": "$14.50",
                "budgeted_currency": 14.5,
                "goal_target_formatted": "$20.00",
                "goal_target_currency": 20.0,
                "goal_under_funded_formatted": "$8.00",
                "goal_under_funded_currency": 8.0,
                "goal_overall_funded_formatted": "$12.00",
                "goal_overall_funded_currency": 12.0,
                "goal_overall_left_formatted": "$8.00",
                "goal_overall_left_currency": 8.0,
                "goal_target_date": CATEGORY_GOAL_TARGET_DATE_1,
            },
            {
                "id": CATEGORY_ID_2,
                "category_group_id": CATEGORY_GROUP_ID_1,
                "category_group_name": CATEGORY_GROUP_NAME_1,
                "name": CATEGORY_NAME_2,
                "balance_formatted": "$9.25",
                "balance_currency": 9.25,
                "activity_formatted": "$1.00",
                "activity_currency": 1.0,
                "budgeted_formatted": "$10.25",
                "budgeted_currency": 10.25,
            },
        ],
    },
    {
        "id": CATEGORY_GROUP_ID_2,
        "name": CATEGORY_GROUP_NAME_2,
        "categories": [
            {
                "id": CATEGORY_ID_3,
                "category_group_id": CATEGORY_GROUP_ID_2,
                "category_group_name": CATEGORY_GROUP_NAME_2,
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
                "name": CATEGORY_NAME_4,
                "balance_formatted": "$19.00",
                "balance_currency": 19.0,
                "activity_formatted": "$19.00",
                "activity_currency": 19.0,
                "budgeted_formatted": "$20.00",
                "budgeted_currency": 20.0,
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
TRANSACTION_ID_3 = str(uuid4())

SUBTRANSACTION_ID_1 = str(uuid4())
SUBTRANSACTION_ID_2 = str(uuid4())

TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": TRANSACTION_ID_1,
        "date": "2024-01-01",
        "amount": -10000,
        "amount_formatted": "$10.00",
        "amount_currency": 10.0,
        "category_id": CATEGORY_ID_3,
        "category_name": CATEGORY_NAME_3,
        "deleted": False,
        "subtransactions": [
            {
                "id": SUBTRANSACTION_ID_1,
                "transaction_id": TRANSACTION_ID_1,
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
                "amount": -2500,
                "amount_formatted": "$2.50",
                "amount_currency": 2.5,
                "category_id": CATEGORY_ID_2,
                "category_name": CATEGORY_NAME_2,
                "deleted": False,
            },
        ],
    },
    {
        "id": TRANSACTION_ID_2,
        "date": "2024-02-01",
        "amount": -15000,
        "amount_formatted": "$15.00",
        "amount_currency": 15.0,
        "category_id": CATEGORY_ID_2,
        "category_name": CATEGORY_NAME_2,
        "deleted": True,
        "subtransactions": [],
    },
    {
        "id": TRANSACTION_ID_3,
        "date": "2024-03-01",
        "amount": -19000,
        "amount_formatted": "$19.00",
        "amount_currency": 19.0,
        "category_id": CATEGORY_ID_4,
        "category_name": CATEGORY_NAME_4,
        "deleted": False,
        "subtransactions": [],
    },
]

SCHEDULED_TRANSACTION_ID_1 = str(uuid4())
SCHEDULED_TRANSACTION_ID_2 = str(uuid4())
SCHEDULED_TRANSACTION_ID_3 = str(uuid4())

SCHEDULED_SUBTRANSACTION_ID_1 = str(uuid4())
SCHEDULED_SUBTRANSACTION_ID_2 = str(uuid4())

SCHEDULED_TRANSACTIONS: list[dict[str, Any]] = [
    {
        "id": SCHEDULED_TRANSACTION_ID_1,
        "amount": -12000,
        "amount_formatted": "$12.00",
        "amount_currency": 12.0,
        "frequency": "monthly",
        "category_id": CATEGORY_ID_1,
        "category_name": CATEGORY_NAME_1,
        "deleted": False,
        "subtransactions": [
            {
                "id": SCHEDULED_SUBTRANSACTION_ID_1,
                "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "deleted": False,
                "amount": -8040,
                "amount_formatted": "$8.04",
                "amount_currency": 8.04,
                "category_id": CATEGORY_ID_2,
                "category_name": CATEGORY_NAME_2,
            },
            {
                "id": SCHEDULED_SUBTRANSACTION_ID_2,
                "scheduled_transaction_id": SCHEDULED_TRANSACTION_ID_1,
                "deleted": False,
                "amount": -2960,
                "amount_formatted": "$2.96",
                "amount_currency": 2.96,
                "category_id": CATEGORY_ID_3,
                "category_name": CATEGORY_NAME_3,
            },
        ],
    },
    {
        "id": SCHEDULED_TRANSACTION_ID_2,
        "amount": -11000,
        "amount_formatted": "$11.00",
        "amount_currency": 11.0,
        "frequency": "yearly",
        "category_id": CATEGORY_ID_3,
        "category_name": CATEGORY_NAME_3,
        "deleted": True,
        "subtransactions": [],
    },
    {
        "id": SCHEDULED_TRANSACTION_ID_3,
        "amount": -9000,
        "amount_formatted": "$9.00",
        "amount_currency": 9.0,
        "frequency": "everyOtherMonth",
        "category_id": CATEGORY_ID_4,
        "category_name": CATEGORY_NAME_4,
        "deleted": False,
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
PLANS_ENDPOINT_RE = re.compile(".+/plans$")
ACCOUNTS_ENDPOINT_RE = re.compile(".+/accounts$")
CATEGORIES_ENDPOINT_RE = re.compile(".+/categories$")
PAYEES_ENDPOINT_RE = re.compile(".+/payees$")
TRANSACTIONS_ENDPOINT_RE = re.compile(".+/transactions$")
SCHEDULED_TRANSACTIONS_ENDPOINT_RE = re.compile(".+/scheduled_transactions$")
