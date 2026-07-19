"use client";

/** Overlay showing one transaction's summary plus its receipt panel.
 * Built on Radix's Dialog primitive (components/ui/Dialog.tsx): focus trap,
 * focus restoration to the triggering row on close, Escape, outside-click,
 * scroll lock, and ARIA wiring all come from Radix — this component only
 * supplies the content. The parent (transactions/page.tsx) mounts this
 * only while a transaction is selected, so `open` is always true here;
 * onOpenChange fires (with `false`) for every way Radix can close the
 * dialog — Escape, outside click, or the close button below — and all of
 * them route through the same `onClose` prop. */

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import type { Account, Category, Transaction } from "@/lib/api/types";
import { formatDate, formatMoney, toNumber } from "@/lib/format";

import { LabelsPanel } from "./LabelsPanel";
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
  const inflow = toNumber(transaction.amount) < 0;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogDescription>
          Transaction details for{" "}
          {transaction.merchant_name ?? "this transaction"}, including receipt
          attachments.
        </DialogDescription>

        <div className="flex items-start justify-between border-b border-line px-5 py-4">
          <div>
            <DialogTitle>
              {transaction.merchant_name ?? "Unknown merchant"}
            </DialogTitle>
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
            <DialogClose asChild>
              <button
                type="button"
                aria-label="Close"
                className="rounded-md px-2 py-1 text-ink-3 hover:bg-line hover:text-ink"
              >
                ✕
              </button>
            </DialogClose>
          </div>
        </div>

        <div className="border-b border-line px-5 py-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-3">
            Labels
          </h4>
          <LabelsPanel transactionId={transaction.id} />
        </div>

        <div className="px-5 py-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-3">
            Receipt
          </h4>
          <ReceiptPanel transactionId={transaction.id} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
