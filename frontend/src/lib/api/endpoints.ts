/** Typed functions for every backend endpoint. */

import { apiGet, apiPost } from "./client";
import type {
  Account,
  AccountsSyncResponse,
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
  User,
} from "./types";

export const api = {
  createUser: (email: string) => apiPost<User>("/users", { email }),

  createLinkToken: (userId: string) =>
    apiPost<LinkTokenResponse>("/plaid/link-token", { user_id: userId }),

  exchangePublicToken: (userId: string, publicToken: string) =>
    apiPost<PlaidItem>("/plaid/exchange-token", {
      user_id: userId,
      public_token: publicToken,
    }),

  syncAccounts: (userId: string, itemId?: string) =>
    apiPost<AccountsSyncResponse>("/plaid/accounts/sync", {
      user_id: userId,
      item_id: itemId ?? null,
    }),

  syncTransactions: (userId: string, itemId?: string) =>
    apiPost<TransactionsSyncResponse>("/transactions/sync", {
      user_id: userId,
      item_id: itemId ?? null,
    }),

  listAccounts: (userId: string, itemId?: string) =>
    apiGet<Account[]>("/accounts", { user_id: userId, item_id: itemId }),

  listTransactions: (params: TransactionListParams) =>
    apiGet<PaginatedTransactions>("/transactions", { ...params }),

  listCategories: () => apiGet<Category[]>("/categories"),

  monthlySpending: (
    userId: string,
    opts: { start_date?: string; end_date?: string; account_id?: string } = {},
  ) =>
    apiGet<MonthlySpendingResponse>("/analytics/monthly-spending", {
      user_id: userId,
      ...opts,
    }),

  categoryBreakdown: (
    userId: string,
    opts: { start_date?: string; end_date?: string } = {},
  ) =>
    apiGet<CategoryBreakdownResponse>("/analytics/category-breakdown", {
      user_id: userId,
      ...opts,
    }),

  topMerchants: (
    userId: string,
    opts: { start_date?: string; end_date?: string; limit?: number } = {},
  ) =>
    apiGet<TopMerchantsResponse>("/analytics/top-merchants", {
      user_id: userId,
      ...opts,
    }),

  monthOverMonth: (userId: string, months?: number) =>
    apiGet<MonthOverMonthResponse>("/analytics/month-over-month", {
      user_id: userId,
      months,
    }),
};
