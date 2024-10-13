from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4

import pytest

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

LKOS = {
    BUDGET_ID_1: 107667,
    BUDGET_ID_2: 107668,
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


@pytest.fixture
def cur():
    with sqlite3.connect(":memory:") as con:
        cursor = con.cursor()
        cursor.executescript(contents("create-tables.sql"))
        cursor.row_factory = lambda c, row: dict(
            zip([name for name, *_ in c.description], row, strict=True)
        )
        yield cursor


def strip_nones(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}
