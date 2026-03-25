# sqlite-export-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/sqlite-export-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/sqlite-export-for-ynab/main) [![codecov](https://codecov.io/github/mxr/sqlite-export-for-ynab/graph/badge.svg?token=NVCP6RDKSH)](https://codecov.io/github/mxr/sqlite-export-for-ynab)

SQLite Export for YNAB - Export YNAB Budget Data to SQLite

## What This Does

Export all your [YNAB](https://ynab.com/) plans to a local [SQLite](https://www.sqlite.org/) DB. Then you can query your data with any tools compatible with SQLite.

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

Run the tool from the terminal to download your plans:

```console
$ sqlite-export-for-ynab
```

Running it again will pull only data that changed since the last pull (this is done with [Delta Requests](https://api.ynab.com/#deltas)). If you want to wipe the DB and pull all data again use the `--full-refresh` flag.

<a id="db-path"></a>You can specify the DB path with the following options
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
1. Foreign keys are added as needed (ex: plan ID, transaction ID) so data across plans remains separate.
1. Two new views called `flat_transactions` and `scheduled_flat_transactions`. These allow you to query split and non-split transactions easily, without needing to also query `subtransactions` and `scheduled_subtransactions` respectively. They also include fields to improve quality of life (ex: `amount_major` to convert from [YNAB's milliunits](https://api.ynab.com/#formats) to [major units](https://en.wikipedia.org/wiki/ISO_4217) i.e. dollars) and filter out deleted transactions/subtransactions.

## Querying

You can issue queries with typical SQLite tools. *`sqlite-export-for-ynab` deliberately does not implement a SQL REPL.*

### Sample Queries

You can run the queries from this README using a tool like [`mdq`](https://github.com/yshavit/mdq). For example:

```console
$ mdq '```sql dupes' path/to/sqlite-export-for-ynab/README.md -o plain \
    | sqlite3 path/to/sqlite-export-for-ynab/db.sqlite
```

The DB path is documented [above](#db-path).

To get the top 5 payees by spending per plan, you could do:

```sql
WITH
ranked_payees AS (
    SELECT
        pl.name AS plan_name
        , t.payee_name AS payee
        , SUM(t.amount_major) AS net_spent
        , ROW_NUMBER() OVER (
            PARTITION BY
                pl.id
            ORDER BY
                SUM(t.amount) ASC
        ) AS rnk
    FROM
        flat_transactions AS t
    INNER JOIN plans AS pl
        ON t.plan_id = pl.id
    WHERE
        t.payee_name != 'Starting Balance'
        AND t.transfer_account_id IS NULL
    GROUP BY
        pl.id
        , t.payee_id
)

SELECT
    plan_name
    , payee
    , net_spent
FROM
    ranked_payees
WHERE
    rnk <= 5
ORDER BY
    plan_name ASC
    , net_spent DESC
;
```

To get duplicate payees, or payees with no transactions:

```sql
SELECT DISTINCT
    pl.name AS "plan"
    , dupes.name AS payee
FROM (
    SELECT DISTINCT
        p.plan_id
        , p.name
    FROM payees AS p
    LEFT JOIN flat_transactions AS ft
        ON
            p.plan_id = ft.plan_id
            AND p.id = ft.payee_id
    LEFT JOIN scheduled_flat_transactions AS sft
        ON
            p.plan_id = sft.plan_id
            AND p.id = sft.payee_id
    WHERE
        TRUE
        AND ft.payee_id IS NULL
        AND sft.payee_id IS NULL
        AND p.transfer_account_id IS NULL
        AND p.name != 'Reconciliation Balance Adjustment'
        AND p.name != 'Manual Balance Adjustment'
        AND NOT p.deleted

    UNION ALL

    SELECT
        plan_id
        , name
    FROM payees
    WHERE NOT deleted
    GROUP BY plan_id, name
    HAVING COUNT(*) > 1

) AS dupes
INNER JOIN plans AS pl
    ON dupes.plan_id = pl.id
ORDER BY "plan", payee
;
```

To count the spend for a category (ex: "Apps") between this month and the next 11 months (inclusive):

```sql
SELECT
    plan_id
    , SUM(amount_major) AS amount_major
FROM (
    SELECT
        plan_id
        , amount_major
    FROM flat_transactions
    WHERE
        category_name = 'Apps'
        AND SUBSTR("date", 1, 7) = SUBSTR(DATE(), 1, 7)
    UNION ALL
    SELECT
        plan_id
        , amount_major * (
            CASE
                WHEN frequency = 'monthly' THEN 11
                ELSE 1 -- assumes yearly
            END
        ) AS amount_major
    FROM scheduled_flat_transactions
    WHERE
        category_name = 'Apps'
        AND SUBSTR(date_next, 1, 7) < SUBSTR(DATE('now', '+1 year'), 1, 7)
)
;
```

To estimate taxable interest for a given year[^1]:

```sql
-- Parameters expected by this query:
--   @tax_rate
--   @year
--   @plan_id (optional, defaults to output for all plans)
--   @estimated_additional_interest (optional, estimated interest not in YNAB such as investment income)
--   @interest_payee_name (optional, defaults to Interest)
--
-- Example with only required params:
-- sqlite3 -header -box path/to/db.sqlite3 \
--   -cmd '.parameter init' \
--   -cmd ".parameter set @tax_rate 0.25" \
--   -cmd ".parameter set @year 2025" \
--   < query.sql
--
-- Example with all params:
--   -cmd ".parameter set @tax_rate 0.25" \
--   -cmd ".parameter set @year 2025" \
--   -cmd ".parameter set @estimated_additional_interest 250.00" \
--   -cmd ".parameter set @interest_payee_name Interest" \
--   -cmd ".parameter set @plan_id your-plan-id" \
--   < query.sql

WITH interest_by_account AS (
    SELECT
        plan_id,
        account_name,
        SUM(-amount_major) AS total
    FROM flat_transactions
    WHERE TRUE
        AND payee_name = COALESCE(NULLIF(@interest_payee_name, ''), 'Interest')
        AND SUBSTR(date, 1, 4) = CAST(@year AS TEXT)
        AND (COALESCE(@plan_id, '') = '' OR plan_id = @plan_id)
    GROUP BY 1, 2
    HAVING total >= 10 -- Common 1099-INT reporting threshold; confirm with actual tax documents
),
interest_by_plan AS (
    SELECT
        plans.id AS plan_id,
        plans.name AS plan_name,
        COALESCE(SUM(interest_by_account.total), 0) AS interest_in_ynab
    FROM plans
    LEFT JOIN interest_by_account ON interest_by_account.plan_id = plans.id
    WHERE COALESCE(@plan_id, '') = '' OR plans.id = @plan_id
    GROUP BY 1, 2
),
ranked_interest AS (
    SELECT
        plan_id,
        plan_name,
        interest_in_ynab,
        ROW_NUMBER() OVER (ORDER BY plan_name, plan_id) AS row_num
    FROM interest_by_plan
)
SELECT
    plan_name AS "plan",
    ROUND(interest_in_ynab, 2) AS interest_in_ynab,
    ROUND(
        CASE
            WHEN row_num <> 1 THEN interest_in_ynab
            WHEN interest_in_ynab + CAST(COALESCE(@estimated_additional_interest, 0) AS REAL) < 10 THEN 0
            ELSE interest_in_ynab + CAST(COALESCE(@estimated_additional_interest, 0) AS REAL)
        END,
        2
    ) AS estimated_total_taxable_interest,
    CASE
        WHEN NULLIF(@tax_rate, '') IS NULL THEN NULL
        ELSE ROUND(
            (
                CASE
                    WHEN row_num <> 1 THEN interest_in_ynab
                    WHEN interest_in_ynab + CAST(COALESCE(@estimated_additional_interest, 0) AS REAL) < 10 THEN 0
                    ELSE interest_in_ynab + CAST(COALESCE(@estimated_additional_interest, 0) AS REAL)
                END
            ) * CAST(@tax_rate AS REAL),
            2
        )
    END AS estimated_tax_liability
FROM ranked_interest
ORDER BY plan_name, plan_id;
```

[^1]: This query is a rough estimate based on YNAB data and optional user inputs. It is not financial advice, tax advice, or a substitute for Forms 1099-INT, brokerage statements, bank records, or guidance from a qualified professional.
