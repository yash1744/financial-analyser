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


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
