"use client";

/** Overlay showing one transaction's summary plus its receipt panel.
 * Closes on backdrop click or Escape. */

import { useEffect } from "react";

import type { Account, Category, Transaction } from "@/lib/api/types";
import { formatDate, formatMoney, toNumber } from "@/lib/format";

import { ReceiptPanel } from "./ReceiptPanel";

export function TransactionDetailModal({
  transaction,
  account,
  category,
  onClose,
}: {
  transaction: Transaction;
  account?: Account;
  category?: Category;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const inflow = toNumber(transaction.amount) < 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:p-8"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="my-auto w-full max-w-2xl rounded-xl border border-line bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Transaction details"
      >
        <div className="flex items-start justify-between border-b border-line px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-ink">
              {transaction.merchant_name ?? "Unknown merchant"}
            </h3>
            <p className="mt-0.5 text-xs text-ink-3">
              {formatDate(transaction.transaction_date)}
              {account ? ` · ${account.name}` : ""}
              {category ? ` · ${category.name}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`text-sm font-medium tabular-nums ${inflow ? "text-good" : "text-ink"}`}
            >
              {inflow ? "+" : "−"}
              {formatMoney(
                Math.abs(toNumber(transaction.amount)),
                transaction.currency,
              )}
            </span>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md px-2 py-1 text-ink-3 hover:bg-line hover:text-ink"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="px-5 py-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-3">
            Receipt
          </h4>
          <ReceiptPanel transactionId={transaction.id} />
        </div>
      </div>
    </div>
  );
}
