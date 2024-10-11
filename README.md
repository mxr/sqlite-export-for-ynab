# sqlite-export-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/sqlite-export-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/sqlite-export-for-ynab/main)

SQLite Export for YNAB - Export YNAB Budget Data to SQLite

## What This Does

Export your [YNAB](https://ynab.com/) budget to a local [SQLite](https://www.sqlite.org/) DB. Then you can query your budget with any tools compatible with SQLite.

## Installation

```console
$ pip install sqlite-export-for-ynab
```

## Usage

Provision a [YNAB Personal Access Token](https://api.ynab.com/#personal-access-tokens) and save it as an environment variable.

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Run the tool from the terminal to download your budget:

```console
$ sqlite-export-for-ynab
```

Running it again will pull only the data that changed since the last pull. If you want to wipe the DB and pull all data again use the `--full-refresh` flag.

You can specify the DB path with `--db`. Otherwise, the DB is stored according to the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/index.html).
If `XDG_DATA_HOME` is set then the DB is saved in `"${XDG_DATA_HOME}"/sqlite-export-for-ynab/db.sqlite`.
If not, then the DB is saved in `~/.local/share/sqlite-export-for-ynab/db.sqlite`.

## SQL

The schema is defined in [create-tables.sql](sqlite_export_for_ynab/ddl/create-tables.sql). It is very similar to [YNAB's OpenAPI Spec](https://api.ynab.com/papi/open_api_spec.yaml) however some objects are pulled out into their own tables (ex: subtransactions, loan account periodic values) and foreign keys are added as needed (ex: budget ID, transaction ID).

You can query the DB with typical SQLite tools. For example, to get the top 5 payees by spending per budget, you could do:

```sql
WITH
    ranked_payees AS (
        SELECT
            b.name AS budget_name,
            p.name AS payee,
            SUM(t.amount) / -1000.0 AS net_spent,
            ROW_NUMBER() OVER (
                PARTITION BY
                    b.id
                ORDER BY
                    SUM(t.amount) ASC
            ) AS rnk
        FROM
            transactions t
            JOIN payees p ON t.payee_id = p.id
            JOIN budgets b ON t.budget_id = b.id
        WHERE
            p.name != 'Starting Balance'
            AND p.transfer_account_id IS NULL
            AND NOT t.deleted
        GROUP BY
            b.id,
            p.id
    )
SELECT
    budget_name,
    payee,
    net_spent
FROM
    ranked_payees
WHERE
    rnk <= 5
ORDER BY
    budget_name,
    net_spent DESC
;
```

To get payees with no transactions:

```sql
SELECT DISTINCT
    b.name,
    p.name
FROM
    budgets b
    JOIN payees p ON b.id = p.budget_id
    LEFT JOIN (
        SELECT
            budget_id,
            payee_id,
            MAX(NOT deleted) AS has_active_transaction
        FROM
            transactions
        GROUP BY
            budget_id,
            payee_id
    ) t ON (
        p.id = t.payee_id
        AND p.budget_id = t.budget_id
    )
WHERE
    not p.deleted 
    AND (
        t.payee_id IS NULL
        OR not t.has_active_transaction 
    )
ORDER BY
    1,
    2
;
```
