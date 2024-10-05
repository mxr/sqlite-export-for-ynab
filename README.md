# sqlite-export-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/sqlite-export-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/sqlite-export-for-ynab/main)

SQLite Export for YNAB - Export YNAB Budget Data to SQLite

## What this Does

Export your [YNAB](https://ynab.com/) budget to a local [SQLite](https://www.sqlite.org/) DB

## Installation

```console
$ pip install sqlite-export-for-ynab
```

## Usage

Run it from the terminal to download your budget:

```console
$ sqlite-export-for-ynab
```

Running it again will pull only the data that changed since the last pull. If you want to wipe the DB and pull all data again use the `--full-refresh` flag.

The DB is stored according to the [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/index.html).

By default the DB is saved in `"${XDG_DATA_HOME}"/sqlite-export-for-ynab/db.sqlite`.
If you don't set `XDG_DATA_HOME` then by default the DB will be saved in `~/.local/share/sqlite-export-for-ynab/db.sqlite`.

Use the `--db` argument to specify a different DB path.

## SQL

The schema is defined in [create-tables.sqlite](sqlite_export_for_ynab/ddl/create-tables.sqlite). It is very similar to [YNAB's OpenAPI Spec](https://api.ynab.com/papi/open_api_spec.yaml) however some objects are pulled out into their own tables (ex: subtransactions, loan account period values) and foreign keys are added as needed (ex: budget ID, transaction ID).

You can query the DB with typical SQLite tools. For example, to get the top 5 payees by spending per budget, you could do:

```sql
WITH
    ranked_payees AS (
        SELECT
            b.id AS budget_id,
            b.name AS budget_name,
            p.name AS payee,
            SUM(t.amount) / -1000.0 AS net_spent,
            ROW_NUMBER() OVER (
                PARTITION BY
                    b.id
                ORDER BY
                    SUM(t.amount) ASC
            ) AS RANK
        FROM
            transactions t
            JOIN payees p ON t.payee_id = p.id
            JOIN budgets b ON t.budget_id = b.id
        WHERE
            p.name != 'Starting Balance'
            AND p.transfer_account_id IS NULL
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
    RANK <= 5
ORDER BY
    budget_name,
    net_spent DESC
;
```

