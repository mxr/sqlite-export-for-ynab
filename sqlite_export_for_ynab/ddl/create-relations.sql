CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY
    , name TEXT
    , last_knowledge_of_server INT
)
;

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , balance INT
    , cleared_balance INT
    , closed BOOLEAN
    , debt_original_balance INT
    , deleted BOOLEAN
    , direct_import_in_error BOOLEAN
    , direct_import_linked BOOLEAN
    , last_reconciled_at TEXT
    , name TEXT
    , note TEXT
    , on_budget BOOLEAN
    , transfer_payee_id TEXT
    , type TEXT
    , uncleared_balance INT
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
)
;

CREATE TABLE IF NOT EXISTS account_periodic_values (
    "date" TEXT
    , name TEXT
    , budget_id TEXT
    , account_id TEXT
    , amount INT
    , PRIMARY KEY (date, name, budget_id, account_id)
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
    , FOREIGN KEY (account_id) REFERENCES accounts (id)
)
;

CREATE TABLE IF NOT EXISTS category_groups (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , name TEXT
    , hidden BOOLEAN
    , deleted BOOLEAN
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
)
;

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , category_group_id TEXT
    , category_group_name TEXT
    , name TEXT
    , hidden BOOLEAN
    , original_category_group_id TEXT
    , note TEXT
    , budgeted INT
    , activity INT
    , balance INT
    , goal_type TEXT
    , goal_needs_whole_amount BOOLEAN
    , goal_day INT
    , goal_cadence INT
    , goal_cadence_frequency INT
    , goal_creation_month TEXT
    , goal_target INT
    , goal_target_month TEXT
    , goal_percentage_complete INT
    , goal_months_to_budget INT
    , goal_under_funded INT
    , goal_overall_funded INT
    , goal_overall_left INT
    , deleted BOOLEAN
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
    , FOREIGN KEY (category_group_id) REFERENCES category_groups (id)
)
;

CREATE TABLE IF NOT EXISTS payees (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , name TEXT
    , transfer_account_id TEXT
    , deleted BOOLEAN
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
)
;

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , account_id TEXT
    , account_name TEXT
    , amount INT
    , approved BOOLEAN
    , category_id TEXT
    , category_name TEXT
    , cleared TEXT
    , "date" TEXT
    , debt_transaction_type TEXT
    , deleted BOOLEAN
    , flag_color TEXT
    , flag_name TEXT
    , import_id TEXT
    , import_payee_name TEXT
    , import_payee_name_original TEXT
    , matched_transaction_id TEXT
    , memo TEXT
    , payee_id TEXT
    , payee_name TEXT
    , transfer_account_id TEXT
    , transfer_transaction_id TEXT
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
    , FOREIGN KEY (account_id) REFERENCES accounts (id)
    , FOREIGN KEY (category_id) REFERENCES categories (id)
    , FOREIGN KEY (payee_id) REFERENCES payees (id)
)
;

CREATE TABLE IF NOT EXISTS subtransactions (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , amount INT
    , category_id TEXT
    , category_name TEXT
    , deleted BOOLEAN
    , memo TEXT
    , payee_id TEXT
    , payee_name TEXT
    , transaction_id TEXT
    , transfer_account_id TEXT
    , transfer_transaction_id TEXT
    , FOREIGN KEY (budget_id) REFERENCES budget (id)
    , FOREIGN KEY (transfer_account_id) REFERENCES accounts (id)
    , FOREIGN KEY (category_id) REFERENCES categories (id)
    , FOREIGN KEY (payee_id) REFERENCES payees (id)
    , FOREIGN KEY (transaction_id) REFERENCES transaction_id (id)
)
;

CREATE VIEW IF NOT EXISTS flat_transactions AS
SELECT
    t.id AS transaction_id
    , st.id AS subtransaction_id
    , t.budget_id
    , t.account_id
    , t.account_name
    , t.approved
    , t.cleared
    , t.date
    , t.debt_transaction_type
    , t.flag_color
    , t.flag_name
    , t.import_id
    , t.import_payee_name
    , t.import_payee_name_original
    , t.matched_transaction_id
    , COALESCE(st.id, t.id) AS id
    , COALESCE(st.amount, t.amount) AS amount
    , COALESCE(st.amount, t.amount) / -1000.0 AS amount_major
    , CASE
        WHEN
            COALESCE(st.transfer_account_id, t.transfer_account_id) IS NULL
            THEN COALESCE(st.category_id, t.category_id)
    END AS category_id
    , CASE
        WHEN
            COALESCE(st.transfer_account_id, t.transfer_account_id) IS NULL
            THEN COALESCE(st.category_name, t.category_name)
    END AS category_name
    , COALESCE(st.memo, t.memo) AS memo
    , COALESCE(st.payee_id, t.payee_id) AS payee_id
    , COALESCE(st.payee_name, t.payee_name) AS payee_name
    , COALESCE(st.transfer_account_id, t.transfer_account_id)
        AS transfer_account_id
    , COALESCE(
        st.transfer_transaction_id
        , t.transfer_transaction_id
    ) AS transfer_transaction_id
FROM
    transactions AS t
LEFT JOIN subtransactions AS st
    ON (
        t.budget_id = st.budget_id
        AND t.id = st.transaction_id
    )
WHERE
    TRUE
    AND NOT t.deleted
    AND NOT st.deleted
;

CREATE TABLE IF NOT EXISTS scheduled_transactions (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , account_id TEXT
    , account_name TEXT
    , amount INT
    , category_id TEXT
    , category_name TEXT
    , date_first TEXT
    , date_next TEXT
    , deleted BOOLEAN
    , flag_color TEXT
    , flag_name TEXT
    , frequency TEXT
    , memo TEXT
    , payee_id TEXT
    , payee_name TEXT
    , transfer_account_id TEXT
    , FOREIGN KEY (budget_id) REFERENCES budgets (id)
    , FOREIGN KEY (account_id) REFERENCES accounts (id)
    , FOREIGN KEY (category_id) REFERENCES categories (id)
    , FOREIGN KEY (payee_id) REFERENCES payees (id)
    , FOREIGN KEY (transfer_account_id) REFERENCES accounts (id)
)
;

CREATE TABLE IF NOT EXISTS scheduled_subtransactions (
    id TEXT PRIMARY KEY
    , budget_id TEXT
    , scheduled_transaction_id TEXT
    , amount INT
    , memo TEXT
    , payee_id TEXT
    , payee_name TEXT
    , category_id TEXT
    , category_name TEXT
    , transfer_account_id TEXT
    , deleted BOOLEAN
    , FOREIGN KEY (budget_id) REFERENCES budget (id)
    , FOREIGN KEY (transfer_account_id) REFERENCES accounts (id)
    , FOREIGN KEY (category_id) REFERENCES categories (id)
    , FOREIGN KEY (payee_id) REFERENCES payees (id)
    , FOREIGN KEY (scheduled_transaction_id) REFERENCES transaction_id (id)
)
;

CREATE VIEW IF NOT EXISTS scheduled_flat_transactions AS
SELECT
    t.id AS transaction_id
    , st.id AS subtransaction_id
    , t.budget_id
    , t.account_id
    , t.account_name
    , t.date_first
    , t.date_next
    , t.flag_color
    , t.flag_name
    , COALESCE(st.payee_name, t.payee_name) AS payee_name
    , COALESCE(st.id, t.id) AS id
    , COALESCE(st.amount, t.amount) AS amount
    , COALESCE(st.amount, t.amount) / -1000.0 AS amount_major
    , CASE
        WHEN
            COALESCE(st.transfer_account_id, t.transfer_account_id) IS NULL
            THEN COALESCE(st.category_id, t.category_id)
    END AS category_id
    , CASE
        WHEN
            COALESCE(st.transfer_account_id, t.transfer_account_id) IS NULL
            THEN COALESCE(st.category_name, t.category_name)
    END AS category_name
    , COALESCE(st.memo, t.memo) AS memo
    , COALESCE(st.payee_id, t.payee_id) AS payee_id
    , COALESCE(st.transfer_account_id, t.transfer_account_id)
        AS transfer_account_id
FROM
    scheduled_transactions AS t
LEFT JOIN scheduled_subtransactions AS st
    ON (
        t.budget_id = st.budget_id
        AND t.id = st.scheduled_transaction_id
    )
WHERE
    TRUE
    AND NOT t.deleted
    AND NOT st.deleted
;
