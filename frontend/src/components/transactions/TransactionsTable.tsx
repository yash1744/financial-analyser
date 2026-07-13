"use client";

import { useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import type { Account, Category, Transaction } from "@/lib/api/types";
import { formatDate, formatMoney, toNumber } from "@/lib/format";

export function TransactionsTable({
  transactions,
  accounts,
  categories,
  faded = false,
}: {
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  /** true while stale data is shown during a page change */
  faded?: boolean;
}) {
  const accountById = useMemo(
    () => new Map(accounts.map((a) => [a.id, a])),
    [accounts],
  );
  const categoryById = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories],
  );

  return (
    <div className="overflow-x-auto">
      <table
        className={`w-full text-sm transition-opacity ${faded ? "opacity-50" : ""}`}
      >
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-3">
            <th className="px-5 py-3 font-medium">Date</th>
            <th className="px-3 py-3 font-medium">Merchant</th>
            <th className="hidden px-3 py-3 font-medium md:table-cell">
              Category
            </th>
            <th className="hidden px-3 py-3 font-medium lg:table-cell">
              Account
            </th>
            <th className="px-3 py-3 font-medium">Status</th>
            <th className="px-5 py-3 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {transactions.map((t) => {
            const inflow = toNumber(t.amount) < 0;
            return (
              <tr key={t.id} className="hover:bg-line/50">
                <td className="whitespace-nowrap px-5 py-3 text-ink-2">
                  {formatDate(t.transaction_date)}
                </td>
                <td className="max-w-[16rem] truncate px-3 py-3 text-ink">
                  {t.merchant_name ?? "Unknown merchant"}
                </td>
                <td className="hidden px-3 py-3 text-ink-2 md:table-cell">
                  {t.category_id
                    ? (categoryById.get(t.category_id)?.name ?? "—")
                    : "Uncategorized"}
                </td>
                <td className="hidden max-w-[12rem] truncate px-3 py-3 text-ink-2 lg:table-cell">
                  {accountById.get(t.account_id)?.name ?? "—"}
                </td>
                <td className="px-3 py-3">
                  {t.pending ? (
                    <Badge tone="warn">pending</Badge>
                  ) : (
                    <Badge>posted</Badge>
                  )}
                </td>
                <td
                  className={`whitespace-nowrap px-5 py-3 text-right font-medium tabular-nums ${
                    inflow ? "text-good" : "text-ink"
                  }`}
                >
                  {inflow ? "+" : "−"}
                  {formatMoney(Math.abs(toNumber(t.amount)), t.currency)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
