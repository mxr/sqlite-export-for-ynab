# sqlite-export-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/sqlite-export-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/sqlite-export-for-ynab/main) [![codecov](https://codecov.io/github/mxr/sqlite-export-for-ynab/graph/badge.svg?token=NVCP6RDKSH)](https://codecov.io/github/mxr/sqlite-export-for-ynab)

SQLite Export for YNAB - Export YNAB Budget Data to SQLite

## What This Does

Export your [YNAB](https://ynab.com/) budget to a local [SQLite](https://www.sqlite.org/) DB. Then you can query your budget with any tools compatible with SQLite.

## Installation

```console
$ pip install sqlite-export-for-ynab
```

## Usage

### CLI

Provision a [YNAB Personal Access Token](https://api.ynab.com/#personal-access-tokens) and save it as an environment variable.

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Run the tool from the terminal to download your budget:

```console
$ sqlite-export-for-ynab
```

Running it again will pull only data that changed since the last pull (this is done with [Delta Requests](https://api.ynab.com/#deltas)). If you want to wipe the DB and pull all data again use the `--full-refresh` flag.

You can specify the DB path with the following options
1. The `--db` flag.
1. The `XDG_DATA_HOME` variable (see the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/index.html)). In that case the DB is saved in `"${XDG_DATA_HOME}"/sqlite-export-for-ynab/db.sqlite`.
1. If neither is set, the DB is saved in `~/.local/share/sqlite-export-for-ynab/db.sqlite`.

### Library

The library exposes the package `sqlite_export_for_ynab` and two functions - `default_db_path` and `sync`. You can use them as follows:

```python
import asyncio
import os

from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

db = default_db_path()
token = os.environ["YNAB_PERSONAL_ACCESS_TOKEN"]
full_refresh = False

asyncio.run(sync(token, db, full_refresh))
```

## Relations

The relations are defined in [create-relations.sql](sqlite_export_for_ynab/ddl/create-relations.sql). They are 1:1 with [YNAB's OpenAPI Spec](https://api.ynab.com/papi/open_api_spec.yaml) (ex: transactions, accounts, etc) with some additions:

1. Some objects are pulled out into their own tables so they can be more cleanly modeled in SQLite (ex: subtransactions, loan account periodic values).
1. Foreign keys are added as needed (ex: budget ID, transaction ID) so data across budgets remains separate.
1. Two new views called `flat_transactions` and `scheduled_flat_transactions`. These allow you to query split and non-split transactions easily, without needing to also query `subtransactions` and `scheduled_subtransactions` respectively. They also include fields to improve quality of life (ex: `amount_major` to convert from [YNAB's milliunits](https://api.ynab.com/#formats) to [major units](https://en.wikipedia.org/wiki/ISO_4217) i.e. dollars) and filter out deleted transactions/subtransactions.

## Querying

You can issue queries with typical SQLite tools. *`sqlite-export-for-ynab` deliberately does not implement a SQL REPL.*

### Sample Queries

To get the top 5 payees by spending per budget, you could do:

```sql
WITH
ranked_payees AS (
    SELECT
        b.name AS budget_name
        , t.payee_name AS payee
        , SUM(t.amount_major) AS net_spent
        , ROW_NUMBER() OVER (
            PARTITION BY
                b.id
            ORDER BY
                SUM(t.amount) ASC
        ) AS rnk
    FROM
        flat_transactions AS t
    INNER JOIN budgets AS b ON t.budget_id = b.id
    WHERE
        t.payee_name != 'Starting Balance'
        AND t.transfer_account_id IS NULL
        AND NOT t.deleted
    GROUP BY
        b.id
        , t.payee_id
)

SELECT
    budget_name
    , payee
    , net_spent
FROM
    ranked_payees
WHERE
    rnk <= 5
ORDER BY
    budget_name ASC
    , net_spent DESC
;
```

To get payees with no transactions:

```sql
WITH st AS (
    SELECT
        budget_id
        , payee_id
        , MAX(NOT deleted) AS has_active_transaction
    FROM
        scheduled_flat_transactions
    GROUP BY
        budget_id
        , payee_id
)

, t AS (
    SELECT
        budget_id
        , payee_id
        , MAX(NOT deleted) AS has_active_transaction
    FROM
        flat_transactions
    GROUP BY
        budget_id
        , payee_id
)

SELECT DISTINCT
    b.name AS budget
    , p.name AS payee
FROM
    budgets AS b
INNER JOIN payees AS p ON b.id = p.budget_id
LEFT JOIN t
    ON (
        p.id = t.payee_id
        AND p.budget_id = t.budget_id
    )
LEFT JOIN st
    ON (
        p.id = st.payee_id
        AND p.budget_id = st.budget_id
    )
WHERE
    NOT p.deleted
    AND p.name != 'Reconciliation Balance Adjustment'
    AND (
        t.payee_id IS NULL
        OR NOT t.has_active_transaction
    )
    AND (
        st.payee_id IS NULL
        OR NOT st.has_active_transaction
    )
ORDER BY
    budget
    , payee
;
```

To count the spend for a category (ex: "Apps") between this month and the next 11 months (inclusive):

```sql
SELECT
    budget_id
    , SUM(amount_major) AS amount_major
FROM (
    SELECT
        budget_id
        , amount_major
    FROM flat_transactions
    WHERE
        NOT deleted
        AND category_name = 'Apps'
        AND SUBSTR(`date`, 1, 7) = SUBSTR(DATE(), 1, 7)
    UNION ALL
    SELECT
        budget_id
        , amount_major
    FROM scheduled_flat_transactions
    WHERE
        NOT deleted
        AND category_name = 'Apps'
        AND SUBSTR(date_next, 1, 7) < SUBSTR(DATE('now', '+1 year'), 1, 7)
)
;
```
