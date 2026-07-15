"""Status enums stored as VARCHAR + CHECK constraint (native_enum=False).

Plain strings with a check constraint migrate far more easily than
Postgres native enums (adding a value is a constraint swap, not an
ALTER TYPE that can't run in a transaction on older PG).
"""

import enum

import sqlalchemy as sa


def str_enum(enum_cls: type[enum.StrEnum]) -> sa.Enum:
    """VARCHAR column constrained to the enum's values via CHECK."""
    return sa.Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=50,
        values_callable=lambda e: [m.value for m in e],
    )


class PlaidItemStatus(enum.StrEnum):
    ACTIVE = "active"
    LOGIN_REQUIRED = "login_required"  # user must re-auth via Link update mode
    ERROR = "error"
    DISCONNECTED = "disconnected"


class ProcessingStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncStatus(enum.StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    ERROR = "error"


class TransactionType(enum.StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionClassification(enum.StrEnum):
    """Financial meaning of a transaction, beyond the debit/credit sign.

    Derived from Plaid's personal_finance_category + amount sign in
    app/services/categorization.py.
    """

    INCOME = "income"  # salary, interest, deposits
    EXPENSE = "expense"  # purchases, bills, subscriptions
    TRANSFER = "transfer"  # between own accounts, credit card payments
    FEE = "fee"  # bank/ATM/service charges
    REFUND = "refund"  # money back against an expense category
    UNKNOWN = "unknown"  # no category data to decide from


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class TokenPurpose(enum.StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
