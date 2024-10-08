CREATE TABLE IF NOT EXISTS budgets (id TEXT primary key, name TEXT, last_knowledge_of_server INT)
;

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT primary key,
    budget_id TEXT,
    balance INT,
    cleared_balance INT,
    closed BOOLEAN,
    debt_original_balance INT,
    deleted BOOLEAN,
    direct_import_in_error BOOLEAN,
    direct_import_linked BOOLEAN,
    last_reconciled_at TEXT,
    name TEXT,
    note TEXT,
    on_budget BOOLEAN,
    transfer_payee_id TEXT,
    TYPE TEXT,
    uncleared_balance INT,
    foreign key (budget_id) references budgets (id)
)
;

CREATE TABLE IF NOT EXISTS account_periodic_values (
    DATE TEXT,
    name TEXT,
    budget_id TEXT,
    account_id TEXT,
    amount INT,
    primary key (DATE, name, budget_id, account_id),
    foreign key (budget_id) references budgets (id),
    foreign key (account_id) references accounts (id)
)
;

CREATE TABLE IF NOT EXISTS category_groups (
    id TEXT primary key,
    budget_id TEXT,
    name TEXT,
    hidden BOOLEAN,
    deleted BOOLEAN,
    foreign key (budget_id) references budgets (id)
)
;

CREATE TABLE IF NOT EXISTS categories (
    id TEXT primary key,
    budget_id TEXT,
    category_group_id TEXT,
    category_group_name TEXT,
    name TEXT,
    hidden BOOLEAN,
    original_category_group_id TEXT,
    note TEXT,
    budgeted INT,
    activity INT,
    balance INT,
    goal_type TEXT,
    goal_needs_whole_amount BOOLEAN,
    goal_day INT,
    goal_cadence INT,
    goal_cadence_frequency INT,
    goal_creation_month text,
    goal_target INT,
    goal_target_month text,
    goal_percentage_complete INT,
    goal_months_to_budget INT,
    goal_under_funded INT,
    goal_overall_funded INT,
    goal_overall_left INT,
    deleted BOOLEAN,
    foreign key (budget_id) references budgets (id),
    foreign key (category_group_id) references category_groups (id)
)
;

CREATE TABLE IF NOT EXISTS payees (
    id TEXT primary key,
    budget_id TEXT,
    name TEXT,
    transfer_account_id TEXT,
    deleted BOOLEAN,
    foreign key (budget_id) references budgets (id)
)
;

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT primary key,
    budget_id TEXT,
    account_id TEXT,
    account_name TEXT,
    amount INT,
    approved BOOLEAN,
    category_id TEXT,
    category_name TEXT,
    cleared TEXT,
    DATE TEXT,
    debt_transaction_type TEXT,
    deleted BOOLEAN,
    flag_color TEXT,
    flag_name TEXT,
    import_id TEXT,
    import_payee_name TEXT,
    import_payee_name_original TEXT,
    matched_transaction_id TEXT,
    memo TEXT,
    payee_id TEXT,
    payee_name TEXT,
    transfer_account_id TEXT,
    transfer_transaction_id TEXT,
    foreign key (budget_id) references budgets (id),
    foreign key (account_id) references accounts (id),
    foreign key (category_id) references categories (id),
    foreign key (payee_id) references payees (id)
)
;

CREATE TABLE IF NOT EXISTS subtransactions (
    id TEXT primary key,
    budget_id TEXT,
    amount INT,
    category_id TEXT,
    category_name TEXT,
    deleted BOOLEAN,
    memo TEXT,
    payee_id TEXT,
    payee_name TEXT,
    transaction_id TEXT,
    transfer_account_id TEXT,
    transfer_transaction_id TEXT,
    foreign key (budget_id) references budget (id),
    foreign key (transfer_account_id) references accounts (id),
    foreign key (category_id) references categories (id),
    foreign key (payee_id) references payees (id),
    foreign key (transaction_id) references transaction_id (id)
)
;

CREATE TABLE IF NOT EXISTS scheduled_transactions (
    id TEXT primary key,
    budget_id TEXT,
    account_id text,
    account_name text,
    amount int,
    category_id text,
    category_name text,
    date_first text,
    date_next text,
    deleted boolean,
    flag_color text,
    flag_name text,
    frequency text,
    memo text,
    payee_id text,
    payee_name text,
    transfer_account_id text,
    foreign key (budget_id) references budgets (id),
    foreign key (account_id) references accounts (id),
    foreign key (category_id) references categories (id),
    foreign key (payee_id) references payees (id),
    foreign key (transfer_account_id) references accounts (id)
)
;

CREATE TABLE IF NOT EXISTS scheduled_subtransactions (
    id TEXT primary key,
    budget_id TEXT,
    scheduled_transaction_id text,
    amount int,
    memo text,
    payee_id text,
    category_id text,
    transfer_account_id text,
    deleted boolean,
    foreign key (budget_id) references budget (id),
    foreign key (transfer_account_id) references accounts (id),
    foreign key (category_id) references categories (id),
    foreign key (payee_id) references payees (id),
    foreign key (scheduled_transaction_id) references transaction_id (id)
)
;
