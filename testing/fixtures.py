from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from sqlite_export_for_ynab._main import contents

BUDGET_ID_1 = str(uuid4())
BUDGET_ID_2 = str(uuid4())

BUDGETS = [
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


@pytest.fixture
def cur():
    with sqlite3.connect(":memory:") as con:
        cursor = con.cursor()
        cursor.executescript(contents("create-tables.sql"))
        cursor.row_factory = lambda c, row: dict(
            zip([name for name, *_ in c.description], row, strict=True)
        )
        yield cursor
