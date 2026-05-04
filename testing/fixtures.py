from __future__ import annotations

from datetime import date
from uuid import UUID
from uuid import uuid4

from asyncio_for_ynab import Account
from asyncio_for_ynab import AccountsResponse
from asyncio_for_ynab import AccountsResponseData
from asyncio_for_ynab import AccountType
from asyncio_for_ynab import CategoriesResponse
from asyncio_for_ynab import CategoriesResponseData
from asyncio_for_ynab import Category
from asyncio_for_ynab import CategoryGroupWithCategories
from asyncio_for_ynab import CurrencyFormat
from asyncio_for_ynab import Payee
from asyncio_for_ynab import PayeesResponse
from asyncio_for_ynab import PayeesResponseData
from asyncio_for_ynab import PlanSummary
from asyncio_for_ynab import PlanSummaryResponse
from asyncio_for_ynab import PlanSummaryResponseData
from asyncio_for_ynab import ScheduledSubTransaction
from asyncio_for_ynab import ScheduledTransactionDetail
from asyncio_for_ynab import ScheduledTransactionsResponse
from asyncio_for_ynab import ScheduledTransactionsResponseData
from asyncio_for_ynab import SubTransaction
from asyncio_for_ynab import TransactionClearedStatus
from asyncio_for_ynab import TransactionDetail
from asyncio_for_ynab import TransactionsResponse
from asyncio_for_ynab import TransactionsResponseData


PLAN_ID_1 = str(uuid4())
PLAN_ID_2 = str(uuid4())

PLANS: list[PlanSummary] = [
    PlanSummary(
        id=UUID(PLAN_ID_1),
        name="Plan 1",
        currency_format=CurrencyFormat(
            currency_symbol="$",
            decimal_digits=2,
            decimal_separator=".",
            display_symbol=True,
            example_format="123,456.78",
            group_separator=",",
            iso_code="USD",
            symbol_first=True,
        ),
    ),
    PlanSummary(
        id=UUID(PLAN_ID_2),
        name="Plan 2",
        currency_format=CurrencyFormat(
            currency_symbol="$",
            decimal_digits=2,
            decimal_separator=".",
            display_symbol=True,
            example_format="123,456.78",
            group_separator=",",
            iso_code="USD",
            symbol_first=True,
        ),
    ),
]

SERVER_KNOWLEDGE_1 = 107667
SERVER_KNOWLEDGE_2 = 107668

LKOS = {
    PLAN_ID_1: SERVER_KNOWLEDGE_1,
    PLAN_ID_2: SERVER_KNOWLEDGE_2,
}

PAYEE_ID_1 = str(uuid4())
PAYEE_ID_2 = str(uuid4())

ACCOUNT_ID_1 = str(uuid4())
ACCOUNT_ID_2 = str(uuid4())

ACCOUNTS: list[Account] = [
    Account(
        id=UUID(ACCOUNT_ID_1),
        name="Account 1",
        type=AccountType.CHECKING,
        on_budget=True,
        closed=False,
        note=None,
        balance=160000,
        cleared_balance=120000,
        uncleared_balance=40000,
        transfer_payee_id=UUID(PAYEE_ID_1),
        direct_import_linked=None,
        direct_import_in_error=None,
        last_reconciled_at=None,
        debt_original_balance=None,
        debt_interest_rates={"2024-02-01": 5000},
        debt_minimum_payments={},
        debt_escrow_amounts={"2024-01-01": 160000},
        deleted=False,
        balance_formatted="$160.00",
        balance_currency=160.0,
        cleared_balance_formatted="$120.00",
        cleared_balance_currency=120.0,
        uncleared_balance_formatted="$40.00",
        uncleared_balance_currency=40.0,
    ),
    Account(
        id=UUID(ACCOUNT_ID_2),
        name="Account 2",
        type=AccountType.SAVINGS,
        on_budget=True,
        closed=False,
        note=None,
        balance=25000,
        cleared_balance=25000,
        uncleared_balance=0,
        transfer_payee_id=UUID(PAYEE_ID_2),
        direct_import_linked=None,
        direct_import_in_error=None,
        last_reconciled_at=None,
        debt_original_balance=None,
        debt_interest_rates={},
        debt_minimum_payments={},
        debt_escrow_amounts={},
        deleted=False,
        balance_formatted="$25.00",
        balance_currency=25.0,
        cleared_balance_formatted="$25.00",
        cleared_balance_currency=25.0,
        uncleared_balance_formatted="$0.00",
        uncleared_balance_currency=0.0,
    ),
]

CATEGORY_GROUP_ID_1 = str(uuid4())
CATEGORY_GROUP_ID_2 = str(uuid4())

CATEGORY_GROUP_NAME_1 = "Category Group 1"
CATEGORY_GROUP_NAME_2 = "Category Group 2"

CATEGORY_ID_1 = str(uuid4())
CATEGORY_ID_2 = str(uuid4())
CATEGORY_ID_3 = str(uuid4())
CATEGORY_ID_4 = str(uuid4())

CATEGORY_NAME_1 = "Category 1"
CATEGORY_NAME_2 = "Category 2"
CATEGORY_NAME_3 = "Category 3"
CATEGORY_NAME_4 = "Category 4"
CATEGORY_GOAL_TARGET_DATE_1 = "2026-12-31"


CATEGORY_GROUPS: list[CategoryGroupWithCategories] = [
    CategoryGroupWithCategories(
        id=UUID(CATEGORY_GROUP_ID_1),
        name=CATEGORY_GROUP_NAME_1,
        hidden=False,
        deleted=False,
        categories=[
            Category(
                id=UUID(CATEGORY_ID_1),
                category_group_id=UUID(CATEGORY_GROUP_ID_1),
                category_group_name=CATEGORY_GROUP_NAME_1,
                name=CATEGORY_NAME_1,
                hidden=False,
                original_category_group_id=None,
                note=None,
                budgeted=14500,
                activity=2500,
                balance=12000,
                goal_type=None,
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=20000,
                goal_target_month=None,
                goal_target_date=date.fromisoformat(CATEGORY_GOAL_TARGET_DATE_1),
                goal_percentage_complete=None,
                goal_months_to_budget=None,
                goal_under_funded=8000,
                goal_overall_funded=12000,
                goal_overall_left=8000,
                goal_snoozed_at=None,
                deleted=False,
                balance_formatted="$12.00",
                balance_currency=12.0,
                activity_formatted="$2.50",
                activity_currency=2.5,
                budgeted_formatted="$14.50",
                budgeted_currency=14.5,
                goal_target_formatted="$20.00",
                goal_target_currency=20.0,
                goal_under_funded_formatted="$8.00",
                goal_under_funded_currency=8.0,
                goal_overall_funded_formatted="$12.00",
                goal_overall_funded_currency=12.0,
                goal_overall_left_formatted="$8.00",
                goal_overall_left_currency=8.0,
            ),
            Category(
                id=UUID(CATEGORY_ID_2),
                category_group_id=UUID(CATEGORY_GROUP_ID_1),
                category_group_name=CATEGORY_GROUP_NAME_1,
                name=CATEGORY_NAME_2,
                hidden=False,
                original_category_group_id=None,
                note=None,
                budgeted=10250,
                activity=1000,
                balance=9250,
                goal_type=None,
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=None,
                goal_target_month=None,
                goal_target_date=None,
                goal_percentage_complete=None,
                goal_months_to_budget=None,
                goal_under_funded=None,
                goal_overall_funded=None,
                goal_overall_left=None,
                goal_snoozed_at=None,
                deleted=False,
                balance_formatted="$9.25",
                balance_currency=9.25,
                activity_formatted="$1.00",
                activity_currency=1.0,
                budgeted_formatted="$10.25",
                budgeted_currency=10.25,
                goal_target_formatted=None,
                goal_target_currency=None,
                goal_under_funded_formatted=None,
                goal_under_funded_currency=None,
                goal_overall_funded_formatted=None,
                goal_overall_funded_currency=None,
                goal_overall_left_formatted=None,
                goal_overall_left_currency=None,
            ),
        ],
    ),
    CategoryGroupWithCategories(
        id=UUID(CATEGORY_GROUP_ID_2),
        name=CATEGORY_GROUP_NAME_2,
        hidden=False,
        deleted=False,
        categories=[
            Category(
                id=UUID(CATEGORY_ID_3),
                category_group_id=UUID(CATEGORY_GROUP_ID_2),
                category_group_name=CATEGORY_GROUP_NAME_2,
                name=CATEGORY_NAME_3,
                hidden=False,
                original_category_group_id=None,
                note=None,
                budgeted=15000,
                activity=7500,
                balance=7500,
                goal_type=None,
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=None,
                goal_target_month=None,
                goal_target_date=None,
                goal_percentage_complete=None,
                goal_months_to_budget=None,
                goal_under_funded=None,
                goal_overall_funded=None,
                goal_overall_left=None,
                goal_snoozed_at=None,
                deleted=False,
                balance_formatted="$7.50",
                balance_currency=7.5,
                activity_formatted="$7.50",
                activity_currency=7.5,
                budgeted_formatted="$15.00",
                budgeted_currency=15.0,
                goal_target_formatted=None,
                goal_target_currency=None,
                goal_under_funded_formatted=None,
                goal_under_funded_currency=None,
                goal_overall_funded_formatted=None,
                goal_overall_funded_currency=None,
                goal_overall_left_formatted=None,
                goal_overall_left_currency=None,
            ),
            Category(
                id=UUID(CATEGORY_ID_4),
                category_group_id=UUID(CATEGORY_GROUP_ID_2),
                category_group_name=CATEGORY_GROUP_NAME_2,
                name=CATEGORY_NAME_4,
                hidden=False,
                original_category_group_id=None,
                note=None,
                budgeted=20000,
                activity=19000,
                balance=19000,
                goal_type=None,
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=None,
                goal_target_month=None,
                goal_target_date=None,
                goal_percentage_complete=None,
                goal_months_to_budget=None,
                goal_under_funded=None,
                goal_overall_funded=None,
                goal_overall_left=None,
                goal_snoozed_at=None,
                deleted=False,
                balance_formatted="$19.00",
                balance_currency=19.0,
                activity_formatted="$19.00",
                activity_currency=19.0,
                budgeted_formatted="$20.00",
                budgeted_currency=20.0,
                goal_target_formatted=None,
                goal_target_currency=None,
                goal_under_funded_formatted=None,
                goal_under_funded_currency=None,
                goal_overall_funded_formatted=None,
                goal_overall_funded_currency=None,
                goal_overall_left_formatted=None,
                goal_overall_left_currency=None,
            ),
        ],
    ),
]

PAYEES: list[Payee] = [
    Payee(id=UUID(PAYEE_ID_1), name="Payee 1", transfer_account_id=None, deleted=False),
    Payee(id=UUID(PAYEE_ID_2), name="Payee 2", transfer_account_id=None, deleted=False),
]

TRANSACTION_ID_1 = str(uuid4())
TRANSACTION_ID_2 = str(uuid4())
TRANSACTION_ID_3 = str(uuid4())

SUBTRANSACTION_ID_1 = str(uuid4())
SUBTRANSACTION_ID_2 = str(uuid4())

TRANSACTIONS: list[TransactionDetail] = [
    TransactionDetail(
        id=TRANSACTION_ID_1,
        date=date.fromisoformat("2024-01-01"),
        amount=-10000,
        memo=None,
        cleared=TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_3),
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        amount_formatted="$10.00",
        amount_currency=10.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_3,
        subtransactions=[
            SubTransaction(
                id=SUBTRANSACTION_ID_1,
                transaction_id=TRANSACTION_ID_1,
                amount=-7500,
                memo=None,
                payee_id=None,
                payee_name=None,
                category_id=UUID(CATEGORY_ID_1),
                category_name=CATEGORY_NAME_1,
                transfer_account_id=None,
                transfer_transaction_id=None,
                deleted=False,
                amount_formatted="$7.50",
                amount_currency=7.5,
            ),
            SubTransaction(
                id=SUBTRANSACTION_ID_2,
                transaction_id=TRANSACTION_ID_1,
                amount=-2500,
                memo=None,
                payee_id=None,
                payee_name=None,
                category_id=UUID(CATEGORY_ID_2),
                category_name=CATEGORY_NAME_2,
                transfer_account_id=None,
                transfer_transaction_id=None,
                deleted=False,
                amount_formatted="$2.50",
                amount_currency=2.5,
            ),
        ],
    ),
    TransactionDetail(
        id=TRANSACTION_ID_2,
        date=date.fromisoformat("2024-02-01"),
        amount=-15000,
        memo=None,
        cleared=TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_2),
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=True,
        amount_formatted="$15.00",
        amount_currency=15.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_2,
        subtransactions=[],
    ),
    TransactionDetail(
        id=TRANSACTION_ID_3,
        date=date.fromisoformat("2024-03-01"),
        amount=-19000,
        memo=None,
        cleared=TransactionClearedStatus.UNCLEARED,
        approved=False,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_4),
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        amount_formatted="$19.00",
        amount_currency=19.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_4,
        subtransactions=[],
    ),
]

SCHEDULED_TRANSACTION_ID_1 = str(uuid4())
SCHEDULED_TRANSACTION_ID_2 = str(uuid4())
SCHEDULED_TRANSACTION_ID_3 = str(uuid4())

SCHEDULED_SUBTRANSACTION_ID_1 = str(uuid4())
SCHEDULED_SUBTRANSACTION_ID_2 = str(uuid4())

SCHEDULED_TRANSACTIONS: list[ScheduledTransactionDetail] = [
    ScheduledTransactionDetail(
        id=UUID(SCHEDULED_TRANSACTION_ID_1),
        date_first=date.fromisoformat("2024-01-01"),
        date_next=date.fromisoformat("2024-01-01"),
        frequency="monthly",
        amount=-12000,
        memo=None,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_1),
        transfer_account_id=None,
        deleted=False,
        amount_formatted="$12.00",
        amount_currency=12.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_1,
        subtransactions=[
            ScheduledSubTransaction(
                id=UUID(SCHEDULED_SUBTRANSACTION_ID_1),
                scheduled_transaction_id=UUID(SCHEDULED_TRANSACTION_ID_1),
                amount=-8040,
                memo=None,
                payee_id=None,
                payee_name=None,
                category_id=UUID(CATEGORY_ID_2),
                category_name=CATEGORY_NAME_2,
                transfer_account_id=None,
                deleted=False,
                amount_formatted="$8.04",
                amount_currency=8.04,
            ),
            ScheduledSubTransaction(
                id=UUID(SCHEDULED_SUBTRANSACTION_ID_2),
                scheduled_transaction_id=UUID(SCHEDULED_TRANSACTION_ID_1),
                amount=-2960,
                memo=None,
                payee_id=None,
                payee_name=None,
                category_id=UUID(CATEGORY_ID_3),
                category_name=CATEGORY_NAME_3,
                transfer_account_id=None,
                deleted=False,
                amount_formatted="$2.96",
                amount_currency=2.96,
            ),
        ],
    ),
    ScheduledTransactionDetail(
        id=UUID(SCHEDULED_TRANSACTION_ID_2),
        date_first=date.fromisoformat("2024-02-01"),
        date_next=date.fromisoformat("2024-02-01"),
        frequency="yearly",
        amount=-11000,
        memo=None,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_3),
        transfer_account_id=None,
        deleted=True,
        amount_formatted="$11.00",
        amount_currency=11.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_3,
        subtransactions=[],
    ),
    ScheduledTransactionDetail(
        id=UUID(SCHEDULED_TRANSACTION_ID_3),
        date_first=date.fromisoformat("2024-03-01"),
        date_next=date.fromisoformat("2024-03-01"),
        frequency="everyOtherMonth",
        amount=-9000,
        memo=None,
        flag_color=None,
        flag_name=None,
        account_id=UUID(ACCOUNT_ID_1),
        payee_id=None,
        category_id=UUID(CATEGORY_ID_4),
        transfer_account_id=None,
        deleted=False,
        amount_formatted="$9.00",
        amount_currency=9.0,
        account_name="Account 1",
        payee_name=None,
        category_name=CATEGORY_NAME_4,
        subtransactions=[],
    ),
]


def plan_response(plans: list[PlanSummary]) -> PlanSummaryResponse:
    return PlanSummaryResponse(data=PlanSummaryResponseData(plans=plans))


def accounts_response(
    accounts: list[Account], server_knowledge: int
) -> AccountsResponse:
    return AccountsResponse(
        data=AccountsResponseData(accounts=accounts, server_knowledge=server_knowledge)
    )


def categories_response(
    category_groups: list[CategoryGroupWithCategories], server_knowledge: int
) -> CategoriesResponse:
    return CategoriesResponse(
        data=CategoriesResponseData(
            category_groups=category_groups, server_knowledge=server_knowledge
        )
    )


def payees_response(payees: list[Payee], server_knowledge: int) -> PayeesResponse:
    return PayeesResponse(
        data=PayeesResponseData(payees=payees, server_knowledge=server_knowledge)
    )


def transactions_response(
    transactions: list[TransactionDetail], server_knowledge: int
) -> TransactionsResponse:
    return TransactionsResponse(
        data=TransactionsResponseData(
            transactions=transactions, server_knowledge=server_knowledge
        )
    )


def scheduled_transactions_response(
    scheduled_transactions: list[ScheduledTransactionDetail], server_knowledge: int
) -> ScheduledTransactionsResponse:
    return ScheduledTransactionsResponse(
        data=ScheduledTransactionsResponseData(
            scheduled_transactions=scheduled_transactions,
            server_knowledge=server_knowledge,
        )
    )


TOKEN = f"token-{uuid4()}"
