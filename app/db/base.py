from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names so Alembic migrations can alter/drop
# them reliably across environments.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from.

    Alembic autogenerate sees models via `import app.models` in
    alembic/env.py — new model modules must be exported from
    app/models/__init__.py to be picked up.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
