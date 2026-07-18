"use client";

import { useMemo, useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { TransactionDetailModal } from "@/components/transactions/TransactionDetailModal";
import { TransactionFilters, type Filters } from "@/components/transactions/TransactionFilters";
import { TransactionsTable } from "@/components/transactions/TransactionsTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { useAccounts, useCategories, useTransactions } from "@/lib/hooks";
import type { Transaction } from "@/lib/api/types";
import { useRequiredUser } from "@/lib/user";

const PAGE_SIZE = 25;

const emptyFilters: Filters = {
  account_id: "",
  category_id: "",
  classification: "",
  merchant: "",
  start_date: "",
  end_date: "",
  min_amount: "",
  max_amount: "",
  sort_by: "transaction_date",
  sort_dir: "desc",
};

export default function TransactionsPage() {
  const user = useRequiredUser();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Transaction | null>(null);

  const accounts = useAccounts(user.id);
  const categories = useCategories();

  const params = useMemo(
    () => ({
      account_id: filters.account_id || undefined,
      category_id: filters.category_id || undefined,
      classification: filters.classification || undefined,
      merchant: filters.merchant || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      min_amount: filters.min_amount || undefined,
      max_amount: filters.max_amount || undefined,
      sort_by: filters.sort_by,
      sort_dir: filters.sort_dir,
      page,
      page_size: PAGE_SIZE,
    }),
    [filters, page],
  );

  const transactions = useTransactions(user.id, params);

  const applyFilters = (next: Filters) => {
    setFilters(next);
    setPage(1);
  };

  const data = transactions.data;
  const isFiltered = JSON.stringify(filters) !== JSON.stringify(emptyFilters);

  return (
    <>
      <PageHeader
        title="Transactions"
        subtitle={
          data ? `${data.total.toLocaleString()} transactions` : undefined
        }
      />

      <Card className="mb-4">
        <TransactionFilters
          value={filters}
          onChange={applyFilters}
          onReset={() => applyFilters(emptyFilters)}
          accounts={accounts.data ?? []}
          categories={categories.data ?? []}
        />
      </Card>

      <Card className="p-0">
        {transactions.isPending ? (
          <div className="p-5">
            <SkeletonLines lines={8} />
          </div>
        ) : transactions.isError ? (
          <ErrorState
            error={transactions.error}
            onRetry={() => transactions.refetch()}
          />
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title={
              isFiltered
                ? "No transactions match these filters"
                : "No transactions yet"
            }
            hint={
              isFiltered
                ? "Try widening the date range or clearing filters."
                : "Connect a bank and sync to pull in transactions."
            }
          />
        ) : data ? (
          <>
            <TransactionsTable
              transactions={data.items}
              accounts={accounts.data ?? []}
              categories={categories.data ?? []}
              faded={transactions.isPlaceholderData}
              onSelect={setSelected}
              onFilterByMerchant={(merchant) =>
                applyFilters({ ...filters, merchant })
              }
            />
            <div className="flex items-center justify-between border-t border-line px-5 py-3">
              <p className="text-xs text-ink-3">
                Page {data.page} of {Math.max(data.total_pages, 1)}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  disabled={page >= data.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        ) : null}
      </Card>

      {selected && (
        <TransactionDetailModal
          transaction={selected}
          account={accounts.data?.find((a) => a.id === selected.account_id)}
          category={categories.data?.find((c) => c.id === selected.category_id)}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
