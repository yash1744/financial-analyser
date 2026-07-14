/** Typed functions for every backend endpoint. The authenticated user is
 * identified by the Bearer token — no user_id parameters. */

import { apiGet, apiPost } from "./client";
import type {
  Account,
  AccountsSyncResponse,
  AuthResponse,
  Category,
  CategoryBreakdownResponse,
  LinkTokenResponse,
  MonthOverMonthResponse,
  MonthlySpendingResponse,
  PaginatedTransactions,
  PlaidItem,
  TopMerchantsResponse,
  TransactionListParams,
  TransactionsSyncResponse,
} from "./types";

export const api = {
  register: (email: string, password: string) =>
    apiPost<AuthResponse>("/auth/register", { email, password }),

  login: (email: string, password: string) =>
    apiPost<AuthResponse>("/auth/login", { email, password }),

  createLinkToken: () => apiPost<LinkTokenResponse>("/plaid/link-token", {}),

  exchangePublicToken: (publicToken: string) =>
    apiPost<PlaidItem>("/plaid/exchange-token", { public_token: publicToken }),

  syncAccounts: (itemId?: string) =>
    apiPost<AccountsSyncResponse>("/plaid/accounts/sync", {
      item_id: itemId ?? null,
    }),

  syncTransactions: (itemId?: string) =>
    apiPost<TransactionsSyncResponse>("/transactions/sync", {
      item_id: itemId ?? null,
    }),

  listAccounts: (itemId?: string) =>
    apiGet<Account[]>("/accounts", { item_id: itemId }),

  listTransactions: (params: TransactionListParams) =>
    apiGet<PaginatedTransactions>("/transactions", { ...params }),

  listCategories: () => apiGet<Category[]>("/categories"),

  monthlySpending: (
    opts: { start_date?: string; end_date?: string; account_id?: string } = {},
  ) => apiGet<MonthlySpendingResponse>("/analytics/monthly-spending", opts),

  categoryBreakdown: (opts: { start_date?: string; end_date?: string } = {}) =>
    apiGet<CategoryBreakdownResponse>("/analytics/category-breakdown", opts),

  topMerchants: (
    opts: { start_date?: string; end_date?: string; limit?: number } = {},
  ) => apiGet<TopMerchantsResponse>("/analytics/top-merchants", opts),

  monthOverMonth: (months?: number) =>
    apiGet<MonthOverMonthResponse>("/analytics/month-over-month", { months }),
};
