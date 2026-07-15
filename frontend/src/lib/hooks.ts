"use client";

/** React Query hooks for every backend read + the sync/link mutations.
 * The API identifies the user from the Bearer token; userId appears only
 * in query keys so one user's cache never leaks into another's session. */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "./api/endpoints";
import type { Account, TransactionListParams } from "./api/types";

export const queryKeys = {
  accounts: (userId: string) => ["accounts", userId] as const,
  transactions: (userId: string, params: TransactionListParams) =>
    ["transactions", userId, params] as const,
  categories: ["categories"] as const,
  monthlySpending: (userId: string, opts: object) =>
    ["analytics", "monthly-spending", userId, opts] as const,
  categoryBreakdown: (userId: string, opts: object) =>
    ["analytics", "category-breakdown", userId, opts] as const,
  topMerchants: (userId: string, opts: object) =>
    ["analytics", "top-merchants", userId, opts] as const,
  monthOverMonth: (userId: string, months: number | undefined) =>
    ["analytics", "month-over-month", userId, months] as const,
};

export function useAccounts(userId: string) {
  return useQuery({
    queryKey: queryKeys.accounts(userId),
    queryFn: () => api.listAccounts(),
  });
}

export function useTransactions(userId: string, params: TransactionListParams) {
  return useQuery({
    queryKey: queryKeys.transactions(userId, params),
    queryFn: () => api.listTransactions(params),
    placeholderData: (previous) => previous, // keep the table while paging
  });
}

export function useCategories() {
  return useQuery({
    queryKey: queryKeys.categories,
    queryFn: () => api.listCategories(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useMonthlySpending(
  userId: string,
  opts: { start_date?: string; end_date?: string; account_id?: string } = {},
) {
  return useQuery({
    queryKey: queryKeys.monthlySpending(userId, opts),
    queryFn: () => api.monthlySpending(opts),
  });
}

export function useCategoryBreakdown(
  userId: string,
  opts: { start_date?: string; end_date?: string } = {},
) {
  return useQuery({
    queryKey: queryKeys.categoryBreakdown(userId, opts),
    queryFn: () => api.categoryBreakdown(opts),
  });
}

export function useTopMerchants(
  userId: string,
  opts: { start_date?: string; end_date?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: queryKeys.topMerchants(userId, opts),
    queryFn: () => api.topMerchants(opts),
  });
}

export function useMonthOverMonth(userId: string, months?: number) {
  return useQuery({
    queryKey: queryKeys.monthOverMonth(userId, months),
    queryFn: () => api.monthOverMonth(months),
  });
}

/** Sync accounts then transactions, and refresh everything derived. */
export function useFullSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (itemId?: string) => {
      const accounts = await api.syncAccounts(itemId);
      const transactions = await api.syncTransactions(itemId);
      return { accounts, transactions };
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

/** Set or clear an account nickname, updating the accounts cache in place. */
export function useSetAccountNickname(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      accountId,
      nickname,
    }: {
      accountId: string;
      nickname: string | null;
    }) => api.setAccountNickname(accountId, nickname),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        queryKeys.accounts(userId),
        (previous: Account[] | undefined) =>
          previous?.map((a) => (a.id === updated.id ? updated : a)),
      );
    },
  });
}

export function useAccountsSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId?: string) => api.syncAccounts(itemId),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}
