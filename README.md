# finance-app

Personal finance application backend. The full Plaid pipeline works
end-to-end: connect a bank via Link (encrypted access-token storage),
sync accounts, and sync transactions (cursor-based, idempotent, raw
payloads kept for reprocessing, auto-categorized from Plaid's taxonomy).
An LLM chat backend answers questions about the synced data through tool
calls (Anthropic or OpenAI). JWT authentication protects every endpoint,
and all data access is scoped to the authenticated user.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Liveness + DB check (public) |
| POST | `/api/v1/auth/register` | Create an account (email + password) → JWT |
| POST | `/api/v1/auth/login` | Sign in → JWT |
| POST | `/api/v1/auth/logout` | Clear the auth cookie |
| GET | `/api/v1/auth/me` | The authenticated user |
| POST | `/api/v1/auth/verify-email/request` | (Re)send the verification email |
| POST | `/api/v1/auth/verify-email/confirm` | Redeem an emailed verification token |
| POST | `/api/v1/auth/forgot-password` | Email a password-reset link (always 202) |
| POST | `/api/v1/auth/reset-password` | Set a new password via an emailed token |
| POST | `/api/v1/plaid/link-token` | Start the Link flow for a user |
| POST | `/api/v1/plaid/exchange-token` | Exchange `public_token`, persist the connection |
| POST | `/api/v1/plaid/accounts/sync` | Fetch + upsert accounts for one item or all of a user's items |
| POST | `/api/v1/transactions/sync` | Pull transaction changes from Plaid (cursor-based, idempotent) |
| GET | `/api/v1/accounts` | A user's synced accounts (optionally one item's) |
| PATCH | `/api/v1/accounts/{id}` | Set or clear an account nickname (null/blank clears) |
| GET | `/api/v1/transactions` | Filterable, sortable, paginated transactions |
| GET | `/api/v1/transactions/{id}` | A single transaction (scoped to the user) |
| GET | `/api/v1/transactions/{id}/receipt` | The transaction's receipt (details + image metadata), or null |
| PUT | `/api/v1/transactions/{id}/receipt` | Create/replace the receipt's details |
| DELETE | `/api/v1/transactions/{id}/receipt` | Remove the receipt and its stored images |
| POST | `/api/v1/transactions/{id}/receipt/images` | Upload one image (multipart `file`; JPEG/PNG/WebP, ≤10/txn) |
| GET | `/api/v1/transactions/{id}/receipt/images/{image_id}` | The image bytes (auth-gated) |
| DELETE | `/api/v1/transactions/{id}/receipt/images/{image_id}` | Delete one image |
| GET | `/api/v1/categories` | All categories (flat list with parent ids) |
| GET | `/api/v1/analytics/monthly-spending` | Spending / income / net per calendar month |
| GET | `/api/v1/analytics/category-breakdown` | Spending by category with % shares |
| GET | `/api/v1/analytics/top-merchants` | Merchants ranked by total spend |
| GET | `/api/v1/analytics/month-over-month` | Last N months with deltas vs prior month |
| GET | `/api/v1/insights/spending-summary` | Headline totals + top category/merchant for a range |
| GET | `/api/v1/insights/compare-spending` | Baseline vs comparison period with per-category deltas |
| GET | `/api/v1/insights/recurring-transactions` | Detected subscription-like charges with cadence |
| POST | `/api/v1/ai/chat` | Ask the finance assistant a question (JSON response) |
| POST | `/api/v1/ai/chat/stream` | Same, streamed as SSE (`token` / `tool` / `done` events) |

Interactive docs at <http://localhost:8000/docs>. Every endpoint except
`/health` and `/auth/*` requires authentication — the httpOnly auth
cookie (browser) or `Authorization: Bearer <token>` (API clients).

## Authentication & authorization

`POST /auth/register` and `/auth/login` issue a stateless HS256 JWT
(`JWT_SECRET_KEY` in `.env`; an insecure dev default applies when unset,
expiry via `JWT_EXPIRY_HOURS`). The token is delivered two ways at once:
an **httpOnly `SameSite=Lax` cookie** (what the browser app uses — JS can
never read it, so XSS can't exfiltrate the credential, and Lax covers
CSRF) and the response body (for API clients that send it back as
`Authorization: Bearer`; the header wins when both are present).
`POST /auth/logout` clears the cookie. Passwords are bcrypt-hashed
(`app/services/auth.py`); login returns the same 401 for a wrong password
and an unknown email so email existence can't be probed. The
`CurrentUserDep` dependency (`app/api/deps.py`) validates the token on
every protected request and loads the user — request bodies and query
strings never carry a user id, so one user cannot address another's data
at all: reads are scoped through the item→user join, and acting on a
foreign `item_id`/`conversation_id` yields 404 (existence is not leaked;
there are no permission tiers, hence no 403s).

**Email verification & password reset**: registration emails a
verification link; `/auth/forgot-password` emails a reset link and always
answers 202 with the same body so account existence can't be probed.
Both links carry a random single-use token that expires
(`EMAIL_VERIFICATION_TTL_HOURS`, `PASSWORD_RESET_TTL_MINUTES`); only the
SHA-256 hash is stored (`auth_tokens` table), reissuing invalidates the
previous link, and a successful reset kills all outstanding reset tokens.
Unverified users can still log in (this app predates verification —
blocking would lock out existing accounts); clients read `email_verified`
from `/auth/me`. Delivery uses `EMAIL_BACKEND`: `console` (default) logs
the email so the flows work with no SMTP server, `smtp` sends via
`SMTP_*`/`EMAIL_FROM`; links point at `APP_BASE_URL`.

## Receipts

Each transaction can carry one **receipt**: user-entered details (merchant,
date, notes, tax/tip, comments) plus up to **10 images** (JPEG/PNG/WebP).
Details and the transaction summary live in Postgres (`receipts`,
`receipt_images`); image bytes go to object storage. `STORAGE_BACKEND`
selects the backend: `local` writes under `LOCAL_STORAGE_DIR` (dev, no
cloud credentials), `r2` uses **Cloudflare R2** via its S3-compatible API
(`R2_*`). Uploads are validated by declared type, size
(`RECEIPT_MAX_IMAGE_BYTES`), and magic bytes; storage keys are always
server-generated uuid paths (never derived from the filename). Image bytes
are served back through the auth-gated API, never exposed from storage
directly. Everything is scoped through the transaction→account→item→user
chain, so a foreign transaction id is indistinguishable from a missing one
(404).

## Account nicknames

Each account carries an optional user **nickname** (`accounts.nickname`)
alongside Plaid's `name`. `PATCH /accounts/{id}` sets it; a null or
blank value clears it. Account responses return all three of `name` (the
untouched Plaid original), `nickname`, and `display_name` (the nickname
when set, else the name) so clients can render the nickname while still
showing the source name. Plaid syncs only write `name`, so nicknames
survive re-syncs even when the bank renames the account.

## Stack

Python 3.13 · FastAPI · PostgreSQL 17 · SQLAlchemy 2 (async) · Alembic · Pydantic v2 · boto3 (R2) · uv · Docker

## Frontend

`frontend/` holds a Next.js + TypeScript + Tailwind + React Query UI
(dashboard, transactions, accounts, Plaid Link connect flow, analytics,
AI assistant chat with SSE streaming). It proxies `/api/v1/*` to this
backend — see `frontend/README.md`.

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

## Quick start

```bash
cp .env.example .env               # then fill in PLAID_*, TOKEN_ENCRYPTION_KEY,
                                   #   and an LLM key for /ai endpoints (optional)
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

## Production deployment

`docker-compose.prod.yml` runs the hardened stack: **Caddy** (TLS
termination, HSTS/CSP/security headers — `deploy/Caddyfile`) in front of
the standalone **Next.js** server (`frontend/Dockerfile`) and **FastAPI**.
Only Caddy binds host ports; Caddy serves the frontend and routes
`/api/v1/*` straight to the API on the internal network, so the browser
sees one origin and the httpOnly auth cookie stays first-party (with
`ENVIRONMENT=production` it is also `Secure`). The `db-backup` sidecar
from the Backups section runs by default.

```bash
# .env must contain ENVIRONMENT=production, JWT_SECRET_KEY,
# TOKEN_ENCRYPTION_KEY, PLAID_* (and optionally an LLM key)
DOMAIN=finance.example.com ACME_EMAIL=you@example.com \
  docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

A real `DOMAIN` gets automatic Let's Encrypt certificates;
`DOMAIN=localhost` (the default) uses Caddy's internal CA — handy for
verifying the stack locally with `curl -k https://localhost/`.
## Backups

A compose sidecar (`db-backup`, opt-in via the `backup` profile) writes a
compressed `pg_dump` custom-format dump to `./backups/` daily and prunes
dumps older than `BACKUP_KEEP_DAYS` (14):

```bash
docker compose --profile backup up -d db-backup                              # daily loop
docker compose --profile backup run --rm db-backup /scripts/db_backup.sh    # one-shot now
# verify a dump without touching live data (restores into a scratch DB):
docker compose --profile backup run --rm db-backup \
  /scripts/db_restore.sh /backups/<file>.dump finance_restore_test
# disaster recovery (drops + recreates live objects):
docker compose --profile backup run --rm db-backup \
  /scripts/db_restore.sh /backups/<file>.dump finance
```

`./backups/` is a host directory (gitignored) — for production, ship it
off-box (object storage via rclone/cron, or use a managed Postgres with
PITR instead).

## Layout

```
app/
  main.py            # app factory + lifespan (startup/shutdown)
  core/              # cross-cutting concerns: settings (env vars), logging
  api/
    deps.py          # dependency-injection wiring (sessions, services)
    v1/              # versioned routers; routes stay thin
  ai/                # LLM chat backend: agent.py (tool loop), llm_client.py
                     #   (interface + Anthropic adapter), openai_client.py
                     #   (OpenAI adapter), tool_registry.py, chat_service.py,
                     #   prompts.py, schemas.py (provider-neutral types)
  llm/               # tools.py: FinanceToolset (tool defs + execution)
  services/          # business logic: plaid.py (Plaid gateway),
                     #   plaid_link.py (Link flow), account_sync.py,
                     #   transaction_sync.py (write side), queries.py
                     #   (read side), auth.py (passwords + JWTs),
                     #   exceptions.py (typed errors → HTTP mapping
                     #   lives in api/errors.py)
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
   encrypted with `TokenCipher` and stored on `plaid_items`. Update-mode
   re-links (same `item_id`) update the stored token in place; an item
   already connected by another user is rejected (409). A fresh Link
   session for an institution the user already has an **active** item for
   is rejected (409, "X is already connected") — Plaid mints a new
   `item_id` per session, so this is the only place duplicates can be
   caught; the just-created orphan item is released at Plaid
   (best-effort `/item/remove`). If the existing connection is broken
   (`login_required` etc.), the fresh link is allowed as the recovery
   path and the stale item is retired to `disconnected` — retired items
   are skipped by the all-items sync paths. The access token is never
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
   `Decimal(str(v))`, and two enrichments from Plaid's
   `personal_finance_category` (`app/services/categorization.py`):
   `category_id` (primary → parent category, detailed suffix → child, rows
   get-or-created on first sight) and `classification` — the financial
   meaning beyond debit/credit: `income`, `expense`, `transfer` (incl.
   credit-card payments via `LOAN_PAYMENTS`), `fee`, `refund` (money in
   against a spending category), or `unknown` when Plaid sent no category.
   Every sync also re-derives both for the item's still-unenriched rows
   from their raw payloads, so data synced before these features existed
   heals itself.
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

## Finance intelligence

`InsightsService` (`app/services/insights.py`) is the interpretive read
layer: answer-shaped compositions over transaction history, next to
`AnalyticsService` (chart series) and the query services (row retrieval).
All logic lives in the services; three consumers share it:

- **REST**: the `/insights/*` endpoints above (plus `merchant=` text search
  on `GET /transactions` and `account_id=` on category breakdown).
- **LLM tools**: `app/llm/tools.py` — `build_finance_toolset(session,
  user_id)` returns a `FinanceToolset` whose `definitions()` are
  provider-ready `{name, description, input_schema}` dicts and whose
  `execute(name, args)` validates with the same Pydantic params models the
  REST layer uses and calls the same service methods. `user_id` is bound at
  construction and never appears in a tool schema, so the model can only
  read the data of the user it was built for. This is what the AI chat
  agent (below) calls.
- **Scheduled jobs** (future): call the services directly with a session.

The `*Params` models in `app/schemas/insights.py` deliberately exclude
`user_id`; REST query models inherit them and add it. One validation path,
zero duplicated business logic.

Recurring detection: SQL narrows to merchants with ≥ N outflows in the
lookback window (`TransactionRepository.recurring_candidates`), then the
service classifies each merchant — every gap between charges within 4 days
of the median gap, median gap inside a cadence band (weekly / biweekly /
monthly / quarterly / yearly), every amount within ±20% of the median.

## AI chat

`POST /ai/chat` takes `{user_id, message, conversation_id?}` and returns the
assistant's answer plus a tool-call audit trail; omitting `conversation_id`
starts a new conversation, passing it back continues one (history is loaded
from Postgres, so conversations survive restarts). `/ai/chat/stream` is the
same request served as SSE: `token` events (text deltas), `tool` events
(`running` / `completed` / `failed` per call), then one `done` event with the
final message and conversation id.

Architecture (`app/ai/`): `FinanceAgent` runs the model ⇄ tool loop against
two abstractions — `LLMClient` (provider adapter) and `ToolRegistry` (wraps
`FinanceToolset`; invalid arguments and unknown tools come back as readable
error results the model can recover from, never exceptions). `ChatService`
owns persistence: every message — user, assistant (including tool-use
blocks), tool results — lands in `messages` as provider-neutral JSONB, and
only user/assistant text is replayed as context for later turns. Routes,
services, and repositories never see a provider SDK.

Providers: `LLM_PROVIDER=anthropic` (default, `claude-opus-4-8`, adaptive
thinking + prompt caching) or `LLM_PROVIDER=openai` (`gpt-5.1`, Chat
Completions). Set the matching `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in
`.env`; without one the `/ai` endpoints return 503 and everything else runs
normally. Provider failures map to typed errors → HTTP: rate limit 429,
auth/config 503, timeout 504, other provider errors 502.

Tests inject a scripted fake through the `get_llm_client` dependency
override, so `tests/test_ai_chat_api.py` exercises the real agent loop,
tools, SQL, and SSE framing with no key and no network;
`tests/test_openai_client.py` unit-tests the OpenAI wire-format translation.

## Data model

```
users 1──* plaid_items 1──* accounts 1──* transactions *──1 categories (optional)
  │             │                                              └── self-ref parent
  │             ├── 1──1 plaid_sync_state          (one /transactions/sync cursor per item)
  │             └── 1──* raw_plaid_transactions    (verbatim JSONB payloads)
  └── 1──* conversations 1──* messages             (chat history; content is JSONB blocks)
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
