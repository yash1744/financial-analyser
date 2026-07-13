# finance-app

Personal finance application backend. The full Plaid pipeline works
end-to-end: connect a bank via Link (encrypted access-token storage),
sync accounts, and sync transactions (cursor-based, idempotent, raw
payloads kept for reprocessing). Auth, categorization, analytics, and
LLM features land later.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Liveness + DB check |
| POST | `/api/v1/users` | Create a user (temporary scaffolding until auth) |
| POST | `/api/v1/plaid/link-token` | Start the Link flow for a user |
| POST | `/api/v1/plaid/exchange-token` | Exchange `public_token`, persist the connection |
| POST | `/api/v1/plaid/accounts/sync` | Fetch + upsert accounts for one item or all of a user's items |
| POST | `/api/v1/transactions/sync` | Pull transaction changes from Plaid (cursor-based, idempotent) |
| GET | `/api/v1/accounts` | A user's synced accounts (optionally one item's) |
| GET | `/api/v1/transactions` | Filterable, sortable, paginated transactions |
| GET | `/api/v1/categories` | All categories (flat list with parent ids) |
| GET | `/api/v1/analytics/monthly-spending` | Spending / income / net per calendar month |
| GET | `/api/v1/analytics/category-breakdown` | Spending by category with % shares |
| GET | `/api/v1/analytics/top-merchants` | Merchants ranked by total spend |
| GET | `/api/v1/analytics/month-over-month` | Last N months with deltas vs prior month |

Interactive docs at <http://localhost:8000/docs>. `user_id` currently rides
in request bodies; it moves to the auth context once authentication exists.

## Stack

Python 3.13 · FastAPI · PostgreSQL 17 · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · uv · Docker

## Frontend

`frontend/` holds a Next.js + TypeScript + Tailwind + React Query UI
(dashboard, transactions, accounts, Plaid Link connect flow, analytics).
It proxies `/api/v1/*` to this backend — see `frontend/README.md`.

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

## Quick start

```bash
cp .env.example .env               # then fill in PLAID_* and TOKEN_ENCRYPTION_KEY
docker compose up --build          # API on http://localhost:8000, Postgres on :5432
curl http://localhost:8000/api/v1/health
```

Plaid credentials come from <https://dashboard.plaid.com/developers/keys>
(sandbox keys are free); generate the encryption key with the command in
`.env.example`. The app boots fine without them — they're only needed once
Plaid calls happen.

Local development without Docker (Postgres still via compose):

```bash
uv sync
docker compose up -d db
uv run uvicorn app.main:app --reload
uv run pytest
```

Migrations:

```bash
uv run alembic upgrade head                                  # apply schema
uv run alembic revision --autogenerate -m "describe change"  # after model edits
```

## Layout

```
app/
  main.py            # app factory + lifespan (startup/shutdown)
  core/              # cross-cutting concerns: settings (env vars), logging
  api/
    deps.py          # dependency-injection wiring (sessions, services)
    v1/              # versioned routers; routes stay thin
  services/          # business logic: plaid.py (Plaid gateway),
                     #   plaid_link.py (Link flow), account_sync.py,
                     #   transaction_sync.py (write side), queries.py
                     #   (read side), user.py, exceptions.py (typed
                     #   errors → HTTP mapping lives in api/errors.py)
  repositories/      # all DB access; only layer that touches the session
  schemas/           # Pydantic request/response contracts + PlaidService results
  models/            # SQLAlchemy ORM models (one module per table)
  db/                # engine, session factory, declarative Base + naming convention
  utils/             # small shared helpers (crypto.py: token encryption at rest)
alembic/             # migration environment (async), versions/
tests/               # pytest; integration tests hit the real Postgres with a
                     #   faked Plaid gateway (conftest disposes the loop-bound
                     #   engine pool between tests)
```

Request flow: **route → service → repository → database**, with schemas at the
API boundary. Each layer only knows about the one below it, so Plaid sync jobs,
LLM categorization, or a CLI can reuse services without going through HTTP.

## Plaid integration

`PlaidService` (`app/services/plaid.py`) is the only code that talks to
Plaid; it never touches the database. The sync SDK runs inside
`asyncio.to_thread`, and SDK exceptions are translated into the typed
hierarchy in `app/services/exceptions.py` — notably
`PlaidItemLoginRequiredError` (user must redo Link in update mode) and
`PlaidRateLimitError` (retry with backoff).

Authentication flow (orchestrated by `PlaidLinkService`):

1. `POST /plaid/link-token` → short-lived token the frontend feeds to
   Plaid Link; bank credentials go to Plaid, never to us.
2. Link's `onSuccess` returns a one-time **public_token** (low-value, safe
   in the browser).
3. `POST /plaid/exchange-token` → permanent **access_token** + `item_id`,
   encrypted with `TokenCipher` and stored on `plaid_items`. Re-linking the
   same institution updates the stored token in place; an item already
   connected by another user is rejected (409). The access token is never
   returned by any endpoint.
4. If Plaid later demands re-auth, calls fail with 409 /
   `ITEM_LOGIN_REQUIRED` and the item is flagged `login_required`; the user
   redoes Link in update mode.

In sandbox, `PlaidService.create_sandbox_public_token()` skips the Link UI
so the whole flow can be exercised from the backend alone.

## Account sync

`POST /plaid/accounts/sync` (`AccountSyncService`) decrypts the item's
access token, fetches accounts from Plaid, and upserts them keyed on
`plaid_account_id`:

- Repeat syncs never duplicate; renamed accounts update in place; balances
  refresh every sync (floats converted via `Decimal(str(v))`).
- Only `depository` and `credit` account types are stored (checking,
  savings, credit cards); others are skipped and counted in the response —
  extend `ACCOUNT_TYPES_TO_SYNC` to widen.
- `ITEM_LOGIN_REQUIRED` during sync persists `status=login_required` before
  returning 409; the next successful sync flips the item back to `active`.
- Accounts Plaid stops returning are kept (their transaction history still
  matters); closed-account handling will be an `is_active` flag later.

## Transaction sync

`POST /transactions/sync` (`TransactionSyncService`) runs Plaid's
cursor-based `/transactions/sync` per item, all inside one database
transaction:

1. Read the cursor from `plaid_sync_state` (none = full history backfill).
2. Fetch all changes since then (`PlaidService` pages internally and
   restarts on Plaid's mutation-during-pagination error).
3. Land every added/modified payload verbatim in `raw_plaid_transactions`.
4. Normalize into `transactions` — upsert keyed on `plaid_transaction_id`,
   `transaction_type` derived from the amount sign, floats →
   `Decimal(str(v))`.
5. Delete normalized rows Plaid reports as `removed` (raw rows are kept as
   the audit trail).
6. Save `next_cursor` + `last_synced_at`, mark the state `idle`, **commit**.

Error recovery: the cursor commits atomically with the data it describes,
so a crash before the commit leaves the old cursor in place — the next run
refetches the same window and converges (at-least-once delivery + unique
`plaid_transaction_id` = no duplicates, fully idempotent). Plaid failures
mark the sync state `error` (and `ITEM_LOGIN_REQUIRED` also flags the item
`login_required`) before surfacing as 409/502. Transactions belonging to
account types we don't sync (loans etc.) keep their raw row, marked
`skipped`, so they can be reprocessed if the filter widens. If an item has
never synced accounts, the account sync runs automatically first.

## Read APIs

Query services (`app/services/queries.py`) are the read side: they never
call Plaid and never commit, returning DTOs only — ORM models stay behind
the service boundary.

`GET /transactions` supports:

- **Filters**: `account_id`, `category_id`, `start_date`/`end_date`
  (inclusive), `min_amount`/`max_amount` — all combinable; inverted ranges
  are rejected with 422.
- **Sorting**: `sort_by` = `transaction_date` (default) | `amount` |
  `merchant_name`, `sort_dir` = `desc` (default) | `asc`; row id breaks
  ties so pagination is stable.
- **Pagination**: `page` (1-based) + `page_size` (default 50, max 200);
  responses carry `total` and `total_pages`.

All reads are scoped to the requesting `user_id` through the
account → item → user join, so one user can never see another's data.

## Analytics

`AnalyticsRepository` (`app/repositories/analytics.py`) does all aggregation
in SQL — `GROUP BY` with conditional `SUM(CASE …)` — so Python never loops
over individual transactions. `AnalyticsService` adds the derived values:
net, category share %, month-over-month deltas, and zero-filled month
sequences. Money is quantized to 2 decimals at the API boundary.

Definitions: **spending** = sum of positive amounts (Plaid convention:
positive = money out), **income** = sum of negative amounts inverted,
**net** = spending − income. Category breakdown and merchant ranks count
outflow only, so refunds don't distort them; uncategorized spend is its own
bucket.

Index usage: every analytics query is scoped through
`transactions → accounts → plaid_items` — `ix_plaid_items_user_id` finds the
user's items, `ix_accounts_plaid_item_id` their accounts, and
`ix_transactions_account_id_transaction_date` (composite, date DESC) serves
both the join back to transactions and any date-range predicate on it.
Cross-account date filters can use `ix_transactions_transaction_date`;
`ix_transactions_category_id` backs the category grouping/filter. At
single-user data volumes the planner may still choose sequential scans —
the indexes matter as the data grows.

## Data model

```
users 1──* plaid_items 1──* accounts 1──* transactions *──1 categories (optional)
                │                                              └── self-ref parent
                ├── 1──1 plaid_sync_state          (one /transactions/sync cursor per item)
                └── 1──* raw_plaid_transactions    (verbatim JSONB payloads)
```

Sync pipeline: Plaid payloads land verbatim in `raw_plaid_transactions`
(partial index keeps the pending-queue scan fast), then get normalized into
`transactions` — raw history can always be reprocessed when categorization
improves. Deletes cascade down the ownership chain; deleting a category only
nulls out `transactions.category_id`.

Conventions (see `app/models/`):

- UUID primary keys, generated by Postgres (`gen_random_uuid()`).
- `NUMERIC(19,4)` for money, `TIMESTAMPTZ` for all timestamps.
- Status columns are VARCHAR + CHECK via the `str_enum()` helper in
  `app/models/enums.py` — not native PG enums (easier migrations).
- Duplicate prevention: unique `plaid_transaction_id` / `plaid_account_id` /
  `plaid_item_id` constraints back the upsert-by-Plaid-id pattern all sync
  services use.
- Transaction `amount` uses Plaid's sign convention: positive = money out.
- Constraint names come from the naming convention on `Base.metadata`
  (`app/db/base.py`); new model modules must be exported from
  `app/models/__init__.py` so Alembic autogenerate sees them.
