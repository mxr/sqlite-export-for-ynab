create table if not exists budgets (id text primary key, name text, last_knowledge_of_server int);


create table if not exists accounts (id text primary key, budget_id text, balance int, cleared_balance int, closed boolean, debt_original_balance int, deleted boolean, direct_import_in_error boolean, direct_import_linked boolean, last_reconciled_at text, name text, note text, on_budget boolean, transfer_payee_id text, type text, uncleared_balance int, foreign key (budget_id) references budgets (id));


create table if not exists account_periodic_values (date text, name text, budget_id text, account_id text, amount int, primary key (date, name, budget_id, account_id), foreign key (budget_id) references budgets (id), foreign key (account_id) references accounts (id));


create table if not exists category_groups (id text primary key, budget_id text, name text, hidden boolean, deleted boolean, foreign key (budget_id) references budgets (id));


create table if not exists categories (id text primary key, budget_id text, category_group_id text, category_group_name text, name text, hidden boolean, original_category_group_id text, note text, budgeted int, activity int, balance int, goal_type text, goal_needs_whole_amount boolean, goal_day int, goal_cadence int, goal_cadence_frequency int, goal_creation_month text, goal_target int, goal_target_month text, goal_percentage_complete int, goal_months_to_budget int, goal_under_funded int, goal_overall_funded int, goal_overall_left int, deleted boolean, foreign key (budget_id) references budgets (id), foreign key (category_group_id) references category_groups (id));


create table if not exists payees (id text primary key, budget_id text, name text, transfer_account_id text, deleted boolean, foreign key (budget_id) references budgets (id));


create table if not exists transactions (id text primary key, budget_id text, account_id text, account_name text, amount int, approved boolean, category_id text, category_name text, cleared text, date text, debt_transaction_type text, deleted boolean, flag_color text, flag_name text, import_id text, import_payee_name text, import_payee_name_original text, matched_transaction_id text, memo text, payee_id text, payee_name text, transfer_account_id text, transfer_transaction_id text, foreign key (budget_id) references budgets (id), foreign key (account_id) references accounts (id), foreign key (category_id) references categories (id), foreign key (payee_id) references payees (id));


create table if not exists subtransactions (id text primary key, budget_id text, amount int, category_id text, category_name text, deleted boolean, memo text, payee_id text, payee_name text, transaction_id text, transfer_account_id text, transfer_transaction_id text, foreign key (budget_id) references budget (id), foreign key (transfer_account_id) references accounts (id), foreign key (category_id) references categories (id), foreign key (payee_id) references payees (id), foreign key (transaction_id) references transaction_id (id));


create table if not exists scheduled_transactions (id text primary key, budget_id text, account_id text, account_name text, amount int, category_id text, category_name text, date_first text, date_next text, deleted boolean, flag_color text, flag_name text, frequency text, memo text, payee_id text, payee_name text, transfer_account_id text, foreign key (budget_id) references budgets (id), foreign key (account_id) references accounts (id), foreign key (category_id) references categories (id), foreign key (payee_id) references payees (id), foreign key (transfer_account_id) references accounts (id));


create table if not exists scheduled_subtransactions (id text primary key, budget_id text, scheduled_transaction_id text, amount int, memo text, payee_id text, category_id text, transfer_account_id text, deleted boolean, foreign key (budget_id) references budget (id), foreign key (transfer_account_id) references accounts (id), foreign key (category_id) references categories (id), foreign key (payee_id) references payees (id), foreign key (scheduled_transaction_id) references transaction_id (id));
