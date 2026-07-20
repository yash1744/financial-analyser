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
import type {
  Account,
  ReceiptDetailsUpdate,
  Transaction,
  TransactionListParams,
} from "./api/types";

export const queryKeys = {
  accounts: (userId: string) => ["accounts", userId] as const,
  transactions: (userId: string, params: TransactionListParams) =>
    ["transactions", userId, params] as const,
  transaction: (transactionId: string) =>
    ["transactions", "one", transactionId] as const,
  categories: ["categories"] as const,
  labels: ["labels"] as const,
  userCategories: ["user-categories"] as const,
  categoryMappings: ["category-mappings"] as const,
  monthlySpending: (userId: string, opts: object) =>
    ["analytics", "monthly-spending", userId, opts] as const,
  categoryBreakdown: (userId: string, opts: object) =>
    ["analytics", "category-breakdown", userId, opts] as const,
  topMerchants: (userId: string, opts: object) =>
    ["analytics", "top-merchants", userId, opts] as const,
  monthOverMonth: (userId: string, months: number | undefined) =>
    ["analytics", "month-over-month", userId, months] as const,
  receipt: (transactionId: string) => ["receipt", transactionId] as const,
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

/** One transaction, kept fresh independently of whatever list page it was
 * opened from — the detail modal reads labels through this, not through
 * the (possibly stale, filter-scoped) row it was opened with. */
export function useTransactionDetail(transactionId: string) {
  return useQuery({
    queryKey: queryKeys.transaction(transactionId),
    queryFn: () => api.getTransaction(transactionId),
  });
}

export function useLabels() {
  return useQuery({
    queryKey: queryKeys.labels,
    queryFn: () => api.listLabels(),
  });
}

/** Create/rename/delete the caller's labels. Any of the three can change
 * what a transaction's `labels` field shows (a rename changes the name in
 * place, a delete removes the assignment entirely) — invalidate both the
 * labels list and every cached transaction view rather than trying to
 * patch each one. */
export function useLabelManagement() {
  const queryClient = useQueryClient();
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.labels });
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
  };

  const createLabel = useMutation({
    mutationFn: (name: string) => api.createLabel(name),
    onSuccess: invalidateAll,
  });
  const renameLabel = useMutation({
    mutationFn: ({ labelId, name }: { labelId: string; name: string }) =>
      api.renameLabel(labelId, name),
    onSuccess: invalidateAll,
  });
  const deleteLabel = useMutation({
    mutationFn: (labelId: string) => api.deleteLabel(labelId),
    onSuccess: invalidateAll,
  });

  return { createLabel, renameLabel, deleteLabel };
}

/** Assign/remove labels on one transaction. The backend returns the full
 * updated transaction, which is written straight into that transaction's
 * own query cache (instant modal update) — the broader transactions list
 * is invalidated alongside so the table's chips catch up too. */
export function useLabelAssignment(transactionId: string) {
  const queryClient = useQueryClient();
  const onSettled = (updated: Transaction | undefined) => {
    if (updated) {
      queryClient.setQueryData(queryKeys.transaction(transactionId), updated);
    }
    queryClient.invalidateQueries({ queryKey: ["transactions"] });
  };

  const assign = useMutation({
    mutationFn: (labelId: string) => api.assignLabel(transactionId, labelId),
    onSuccess: onSettled,
  });
  const unassign = useMutation({
    mutationFn: (labelId: string) => api.unassignLabel(transactionId, labelId),
    onSuccess: onSettled,
  });

  return { assign, unassign };
}

export function useUserCategories() {
  return useQuery({
    queryKey: queryKeys.userCategories,
    queryFn: () => api.listUserCategories(),
  });
}

/** Create/rename/delete the caller's own rollup categories. Any of the
 * three can change how analytics groups spending (a rename changes the
 * displayed name, a delete drops its mappings via cascade), so both the
 * category list and analytics queries are invalidated. */
export function useUserCategoryManagement() {
  const queryClient = useQueryClient();
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.userCategories });
    queryClient.invalidateQueries({ queryKey: queryKeys.categoryMappings });
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
  };

  const createUserCategory = useMutation({
    mutationFn: (name: string) => api.createUserCategory(name),
    onSuccess: invalidateAll,
  });
  const renameUserCategory = useMutation({
    mutationFn: ({ categoryId, name }: { categoryId: string; name: string }) =>
      api.renameUserCategory(categoryId, name),
    onSuccess: invalidateAll,
  });
  const deleteUserCategory = useMutation({
    mutationFn: (categoryId: string) => api.deleteUserCategory(categoryId),
    onSuccess: invalidateAll,
  });

  return { createUserCategory, renameUserCategory, deleteUserCategory };
}

export function useCategoryMappings() {
  return useQuery({
    queryKey: queryKeys.categoryMappings,
    queryFn: () => api.listCategoryMappings(),
  });
}

/** Assign/remove which user category a Plaid category rolls up into. */
export function useCategoryMappingMutations() {
  const queryClient = useQueryClient();
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.categoryMappings });
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
  };

  const setMapping = useMutation({
    mutationFn: ({
      categoryId,
      userCategoryId,
    }: {
      categoryId: string;
      userCategoryId: string;
    }) => api.setCategoryMapping(categoryId, userCategoryId),
    onSuccess: invalidateAll,
  });
  const removeMapping = useMutation({
    mutationFn: (categoryId: string) => api.removeCategoryMapping(categoryId),
    onSuccess: invalidateAll,
  });

  return { setMapping, removeMapping };
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

export function useReceipt(transactionId: string) {
  return useQuery({
    queryKey: queryKeys.receipt(transactionId),
    queryFn: () => api.getReceipt(transactionId),
  });
}

/** Details save, image upload, and both delete flows for one transaction's
 * receipt. Each mutation writes the fresh receipt (or null) straight into
 * the query cache so the panel updates without a refetch. */
export function useReceiptMutations(transactionId: string) {
  const queryClient = useQueryClient();
  const key = queryKeys.receipt(transactionId);

  const saveDetails = useMutation({
    mutationFn: (details: ReceiptDetailsUpdate) =>
      api.saveReceiptDetails(transactionId, details),
    onSuccess: (receipt) => queryClient.setQueryData(key, receipt),
  });

  const uploadImage = useMutation({
    mutationFn: (file: File) => api.uploadReceiptImage(transactionId, file),
    onSuccess: (receipt) => queryClient.setQueryData(key, receipt),
  });

  const deleteImage = useMutation({
    mutationFn: (imageId: string) =>
      api.deleteReceiptImage(transactionId, imageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  const deleteReceipt = useMutation({
    mutationFn: () => api.deleteReceipt(transactionId),
    onSuccess: () => queryClient.setQueryData(key, null),
  });

  return { saveDetails, uploadImage, deleteImage, deleteReceipt };
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
