# finance-app frontend

Next.js frontend for the FastAPI backend in the repository root.

**Stack**: Next.js (App Router) · TypeScript · Tailwind CSS v4 · TanStack React Query · Recharts · react-plaid-link

## Pages

| Route | Purpose |
|---|---|
| `/` | Dashboard — balance/spending KPI tiles, spending-vs-income chart, recent transactions |
| `/transactions` | Filterable, sortable, paginated transaction table |
| `/accounts` | Synced accounts with balances + manual sync |
| `/connect` | Plaid Link flow: link token → Link UI → exchange → auto-sync |
| `/analytics` | Monthly spending/income, month-over-month trend, category breakdown, top merchants |
| `/assistant` | AI chat over your finances — streamed SSE answers, markdown, tool audit trail |

## Running

The backend must be up on `http://localhost:8000` (see the root README).

```bash
npm install
npm run dev        # http://localhost:3000
```

`next.config.ts` proxies `/api/v1/*` to the backend (no CORS needed). Point it
elsewhere with `BACKEND_URL=http://host:port npm run dev`.

On first load the app shows a login/register gate. The backend returns a
JWT which is kept with the user info in localStorage (`finance.session`)
and sent as an `Authorization: Bearer` header on every request; a 401
clears the session and returns to the gate. "Switch user" in the sidebar
signs out.

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
    user.tsx          # localStorage-backed auth session store (JWT + user)
    format.ts         # money/date formatting (backend Decimals arrive as strings)
```

Design tokens (light + dark via `prefers-color-scheme`) live in
`src/app/globals.css` and are exposed as Tailwind colors (`bg-surface`,
`text-ink`, `bg-series-1`, …). Charts read the same CSS variables, so they
follow the theme automatically.
