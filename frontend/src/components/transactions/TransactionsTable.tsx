"use client";

import { Fragment, useMemo } from "react";

import { Badge } from "@/components/ui/Badge";
import type {
  Account,
  Category,
  Transaction,
  TransactionClassification,
} from "@/lib/api/types";
import { formatDate, formatMoney, toNumber } from "@/lib/format";

// Columns rendered per transaction row (Merchant, Category, Type, Account,
// Status, Amount, chevron) — the date header row spans all of them.
const COLUMN_COUNT = 7;

const CLASSIFICATION_TONES: Record<
  TransactionClassification,
  "neutral" | "good" | "warn" | "bad"
> = {
  income: "good",
  refund: "good",
  fee: "bad",
  expense: "neutral",
  transfer: "neutral",
  unknown: "neutral",
};

interface TransactionGroup {
  date: string;
  transactions: Transaction[];
}

/** Bucket transactions by transaction_date, one header per distinct date.
 * Each date's rows keep their relative order from the input (whatever the
 * active sort is), so this holds regardless of sort_by: under the default
 * date sort, dates are already contiguous and this is a no-op reshuffle;
 * under amount/merchant sort, same-date rows are pulled together (in their
 * sorted relative order) instead of appearing under a repeated header. */
function groupByDate(transactions: Transaction[]): TransactionGroup[] {
  const order: string[] = [];
  const byDate = new Map<string, Transaction[]>();
  for (const t of transactions) {
    const bucket = byDate.get(t.transaction_date);
    if (bucket) {
      bucket.push(t);
    } else {
      byDate.set(t.transaction_date, [t]);
      order.push(t.transaction_date);
    }
  }
  return order.map((date) => ({ date, transactions: byDate.get(date)! }));
}

export function TransactionsTable({
  transactions,
  accounts,
  categories,
  faded = false,
  onSelect,
  onFilterByMerchant,
}: {
  transactions: Transaction[];
  accounts: Account[];
  categories: Category[];
  /** true while stale data is shown during a page change */
  faded?: boolean;
  /** open the detail/receipt view for a transaction */
  onSelect?: (transaction: Transaction) => void;
  /** filter the list down to this merchant name (additive with other
   * active filters — the same effect as picking a value in the filter bar) */
  onFilterByMerchant?: (merchantName: string) => void;
}) {
  const accountById = useMemo(
    () => new Map(accounts.map((a) => [a.id, a])),
    [accounts],
  );
  const categoryById = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories],
  );
  const groups = useMemo(() => groupByDate(transactions), [transactions]);

  return (
    <div className="overflow-x-auto">
      <table
        className={`w-full text-sm transition-opacity ${faded ? "opacity-50" : ""}`}
      >
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-3">
            <th className="px-5 py-3 font-medium">Merchant</th>
            <th className="hidden px-3 py-3 font-medium md:table-cell">
              Category
            </th>
            <th className="px-3 py-3 font-medium">Type</th>
            <th className="hidden px-3 py-3 font-medium lg:table-cell">
              Account
            </th>
            <th className="px-3 py-3 font-medium">Status</th>
            <th className="px-5 py-3 text-right font-medium">Amount</th>
            <th className="w-8 px-3 py-3" aria-label="Receipt" />
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {groups.map((group) => (
            <Fragment key={group.date}>
              <tr className="bg-page">
                <th
                  scope="colgroup"
                  colSpan={COLUMN_COUNT}
                  className="px-5 py-2 text-left text-xs font-semibold text-ink-2"
                >
                  {formatDate(group.date)}
                </th>
              </tr>
              {group.transactions.map((t) => {
                const inflow = toNumber(t.amount) < 0;
                return (
                  // Plain <tr>: interactivity lives on the two buttons
                  // below, not the row — a row-sized click/keyboard target
                  // meant assistive tech saw a table row announced as a
                  // button. Two native buttons need no role/tabIndex/keydown
                  // reimplementation and each has one unambiguous action.
                  <tr key={t.id} className="hover:bg-line/50">
                    <td className="max-w-[16rem] px-5 py-3 text-ink">
                      <div className="truncate">
                        {t.merchant_name && onFilterByMerchant ? (
                          <button
                            type="button"
                            onClick={() => onFilterByMerchant(t.merchant_name!)}
                            title={`Show all "${t.merchant_name}" transactions`}
                            className="truncate text-left hover:underline focus-visible:underline focus-visible:outline-none"
                          >
                            {t.merchant_name}
                          </button>
                        ) : (
                          t.merchant_name ?? "Unknown merchant"
                        )}
                      </div>
                      {t.labels.length > 0 && (
                        <div className="mt-0.5 flex gap-1 truncate">
                          {t.labels.slice(0, 2).map((label) => (
                            <span
                              key={label.id}
                              className="shrink-0 rounded-full bg-line px-1.5 py-0.5 text-[10px] font-medium text-ink-3"
                            >
                              {label.name}
                            </span>
                          ))}
                          {t.labels.length > 2 && (
                            <span className="shrink-0 text-[10px] text-ink-3">
                              +{t.labels.length - 2}
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="hidden px-3 py-3 text-ink-2 md:table-cell">
                      {t.category_id
                        ? (categoryById.get(t.category_id)?.name ?? "—")
                        : "Uncategorized"}
                    </td>
                    <td className="px-3 py-3">
                      <Badge tone={CLASSIFICATION_TONES[t.classification]}>
                        {t.classification}
                      </Badge>
                    </td>
                    <td className="hidden max-w-[12rem] truncate px-3 py-3 text-ink-2 lg:table-cell">
                      {accountById.get(t.account_id)?.display_name ?? "—"}
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
                    <td className="px-3 py-3 text-right">
                      {onSelect && (
                        <button
                          type="button"
                          onClick={() => onSelect(t)}
                          aria-label="View transaction details"
                          className="rounded-md px-1.5 py-1 text-ink-3 hover:bg-line hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                        >
                          ›
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
