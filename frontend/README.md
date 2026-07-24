# finance-app frontend

Next.js frontend for the FastAPI backend in the repository root.

**Stack**: Next.js (App Router) · TypeScript · Tailwind CSS v4 · TanStack React Query · Recharts · react-plaid-link

## Pages

| Route | Purpose |
|---|---|
| `/` | Dashboard — balance/spending KPI tiles, spending-vs-income chart, recent transactions |
| `/transactions` | Filterable, sortable, paginated table grouped under date headers; click a merchant name to filter to that merchant, click the arrow to open detail + receipt + labels |
| `/accounts` | Synced accounts with balances, manual sync, and editable per-account nicknames |
| `/connect` | Plaid Link flow: link token → Link UI → exchange → auto-sync |
| `/analytics` | Monthly spending/income, month-over-month trend, category breakdown, top merchants |
| `/categories` | Create your own rollup categories and assign Plaid's categories to them |
| `/assistant` | AI chat over your finances — streamed SSE answers, markdown, tool audit trail |
| `/verify-email` | Landing page for the emailed verification link (public) |
| `/forgot-password` | Request a password-reset email (public) |
| `/reset-password` | Choose a new password via the emailed link (public) |

## Running

The backend must be up on `http://localhost:8000` (see the root README).

```bash
npm install
npm run dev        # http://localhost:3000
```

`next.config.ts` proxies `/api/v1/*` to the backend (no CORS needed). Point it
elsewhere with `BACKEND_URL=http://host:port npm run dev`.

On first load the app shows a login/register gate. The JWT lives in an
httpOnly cookie set by the backend — JavaScript never sees it; the
browser attaches it to every same-origin request automatically.
localStorage (`finance.profile`) holds only the id/email for display.
A 401 clears the profile and returns to the gate; "Sign out" calls
`/auth/logout` to clear the cookie.

Registration sends an email-verification link and the login form offers a
"Forgot your password?" flow. With the backend's default
`EMAIL_BACKEND=console` the emailed link is printed in the backend logs —
open it in the browser to complete the flow locally. The three auth-flow
routes are public (not behind the login gate).

In Plaid sandbox, banks accept the test credentials `user_good` / `pass_good`.

## Layout

```
src/
  app/                # one folder per route; providers.tsx wires React Query
  components/
    layout/           # sidebar shell, page header
    ui/               # Card, Button, StatTile, Badge, Skeleton, ErrorState, …
    charts/           # Recharts wrappers + HTML BarList; chartTheme.tsx = shared chrome
    transactions/     # filter form + table
    assistant/        # chat UI: window, bubbles, markdown, tool trail, suggestions
    UserGate.tsx      # login/register gate; blocks the app until signed in
  lib/
    api/              # client.ts (fetch + ApiError), endpoints.ts, types.ts,
                      #   assistant.ts (chat + SSE stream parser)
    hooks.ts          # React Query hooks + query keys
    useAssistantChat.ts  # chat transcript reducer + streaming orchestration
    user.tsx          # profile store (JWT stays in an httpOnly cookie)
    format.ts         # money/date formatting (backend Decimals arrive as strings)
```

Design tokens (light + dark via `prefers-color-scheme`) live in
`src/app/globals.css` and are exposed as Tailwind colors (`bg-surface`,
`text-ink`, `bg-series-1`, …). Charts read the same CSS variables, so they
follow the theme automatically.

**Theme toggle**: a System/Light/Dark control in the sidebar (`lib/theme.ts`,
`components/layout/ThemeToggle.tsx`) lets a user override the OS preference,
persisted to `localStorage` and applied as `data-theme` on `<html>` — the
override CSS in `globals.css` is more specific than the `prefers-color-scheme`
media query, so it always wins when set. An inline script in the root layout
applies a stored override before first paint (see Next's ["preventing flash
before hydration"](https://nextjs.org/docs/app/guides/preventing-flash-before-hydration)
guide) — "System" (no stored override) stays a pure CSS media query with zero
JS involved, unchanged from before this existed.

**Accessible dialogs**: the transaction detail modal
(`components/transactions/TransactionDetailModal.tsx`) is built on
[Radix UI's Dialog primitive](https://www.radix-ui.com/primitives/docs/components/dialog)
via a small styled wrapper (`components/ui/Dialog.tsx`) — focus trap, focus
restoration on close, Escape, outside-click, and ARIA wiring all come from
Radix rather than being hand-rolled.

**Transaction row interactions**: each row exposes two separate native
`<button>`s rather than one row-sized click target — the merchant name
(filters the list to that merchant, additive with any other active filters,
same mechanism as picking a value in the filter bar) and a trailing arrow
(opens the detail/receipt dialog above). The `<tr>` itself carries no
click/keyboard handling; both buttons get standard focus/Enter/Space
behavior for free, and each has an explicit accessible name, so the whole
interaction is keyboard-operable without any custom key handling.

**Labels** (`components/transactions/LabelsPanel.tsx`): user-created,
private tags assignable to any number of transactions. The detail modal's
Labels section reads through a dedicated `useTransactionDetail` query
rather than the (possibly stale) row it was opened from, so assign/remove
reflects immediately regardless of which filtered page the row came from;
assigning writes the fresh transaction straight into that query's cache
and invalidates the transactions list so the table's chips catch up too.
The "+ Add label" control is a small hand-rolled combobox (search existing
labels or create one inline) rather than a native `<select>`, since it
needs both free-text creation and click-to-assign in one control.

**Multi-select filters** (`MultiSelectField` in `TransactionFilters.tsx`):
Accounts, Categories, Type, and Labels all share one checkbox-popover
component — checking several values matches any of them (OR) within that
filter, while the different filter fields still combine with AND, same as
before. Selected values render as removable chips under the field (click
the × to drop one) plus a "Clear all" inside the popover, so the active
set stays visible without reopening it. Merchant, date range, and amount
range stay single-value inputs, since "OR" has no obvious meaning for free
text or a range.

**User categories** (`app/categories/page.tsx`): a settings-style page, not
reachable from the transaction workflow the way labels are — assigning a
Plaid category to a group is a rarely-revisited setup task, not a
per-transaction action. Two sections: create/rename/delete your own
categories, and assign each of Plaid's categories to one of them via a
plain `<Select>` (single-value per Plaid category, since
`category_mappings`' primary key enforces at most one user category per
Plaid category). The category-breakdown chart on `/analytics` needed no
changes at all — it already only renders `category_name`, and the backend
resolves the effective (mapped-or-raw) name before the response ever
reaches the frontend.
