# finance-app frontend

Next.js frontend for the FastAPI backend in the repository root.

**Stack**: Next.js (App Router) · TypeScript · Tailwind CSS v4 · TanStack React Query · Recharts · react-plaid-link

## Pages

| Route | Purpose |
|---|---|
| `/` | Dashboard — balance/spending KPI tiles, spending-vs-income chart, recent transactions |
| `/transactions` | Filterable, sortable, paginated table; click a row for its detail + receipt panel |
| `/accounts` | Synced accounts with balances, manual sync, and editable per-account nicknames |
| `/connect` | Plaid Link flow: link token → Link UI → exchange → auto-sync |
| `/analytics` | Monthly spending/income, month-over-month trend, category breakdown, top merchants |
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
