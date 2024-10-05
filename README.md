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
