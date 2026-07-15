/** Typed functions for every backend endpoint. The authenticated user is
 * identified by the Bearer token — no user_id parameters. */

import { apiDelete, apiGet, apiPatch, apiPost, apiPut, apiUpload } from "./client";
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
  Receipt,
  ReceiptDetailsUpdate,
  TopMerchantsResponse,
  TransactionListParams,
  TransactionsSyncResponse,
} from "./types";

export const api = {
  register: (email: string, password: string) =>
    apiPost<AuthResponse>("/auth/register", { email, password }),

  login: (email: string, password: string) =>
    apiPost<AuthResponse>("/auth/login", { email, password }),

  logout: () => apiPost<void>("/auth/logout", {}),

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

  setAccountNickname: (accountId: string, nickname: string | null) =>
    apiPatch<Account>(`/accounts/${accountId}`, { nickname }),

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

  // --- receipts ---

  getReceipt: (transactionId: string) =>
    apiGet<Receipt | null>(`/transactions/${transactionId}/receipt`),

  saveReceiptDetails: (transactionId: string, details: ReceiptDetailsUpdate) =>
    apiPut<Receipt>(`/transactions/${transactionId}/receipt`, details),

  deleteReceipt: (transactionId: string) =>
    apiDelete<void>(`/transactions/${transactionId}/receipt`),

  uploadReceiptImage: (transactionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiUpload<Receipt>(
      `/transactions/${transactionId}/receipt/images`,
      form,
    );
  },

  deleteReceiptImage: (transactionId: string, imageId: string) =>
    apiDelete<void>(
      `/transactions/${transactionId}/receipt/images/${imageId}`,
    ),

  /** Same-origin URL for an image's bytes (auth rides the cookie). */
  receiptImageUrl: (transactionId: string, imageId: string) =>
    `/api/v1/transactions/${transactionId}/receipt/images/${imageId}`,
};
