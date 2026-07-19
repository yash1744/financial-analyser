"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import type {
  Account,
  Category,
  Label,
  SortDir,
  TransactionClassification,
  TransactionSortBy,
} from "@/lib/api/types";

export interface Filters {
  account_id: string;
  category_id: string;
  classification: TransactionClassification | "";
  merchant: string;
  label_ids: string[];
  start_date: string;
  end_date: string;
  min_amount: string;
  max_amount: string;
  sort_by: TransactionSortBy;
  sort_dir: SortDir;
}

/** Every other filter is single-value, a plain <select>. Labels are the
 * first multi-value filter this component has, so they get their own
 * checkbox popover instead — matches any of the checked labels (OR). */
function LabelFilterField({
  labels,
  selected,
  onChange,
}: {
  labels: Label[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const toggle = (id: string) =>
    onChange(
      selected.includes(id)
        ? selected.filter((s) => s !== id)
        : [...selected, id],
    );

  return (
    <Field label="Labels">
      <div className="relative" ref={panelRef}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-left text-sm text-ink hover:border-ink-3"
        >
          {selected.length === 0 ? "All" : `${selected.length} selected`}
        </button>
        {open && (
          <div className="absolute left-0 top-full z-10 mt-1 w-48 rounded-lg border border-line bg-surface p-2 shadow-lg">
            {labels.length === 0 ? (
              <p className="px-1 py-1 text-xs text-ink-3">No labels yet.</p>
            ) : (
              <div className="max-h-48 space-y-0.5 overflow-y-auto">
                {labels.map((label) => (
                  <label
                    key={label.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm text-ink hover:bg-line"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(label.id)}
                      onChange={() => toggle(label.id)}
                      className="accent-accent"
                    />
                    <span className="truncate">{label.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Field>
  );
}

const CLASSIFICATIONS: { value: TransactionClassification; label: string }[] = [
  { value: "income", label: "Income" },
  { value: "expense", label: "Expense" },
  { value: "transfer", label: "Transfer" },
  { value: "fee", label: "Fee" },
  { value: "refund", label: "Refund" },
  { value: "unknown", label: "Unknown" },
];

export function TransactionFilters({
  value,
  onChange,
  onReset,
  accounts,
  categories,
  labels,
}: {
  value: Filters;
  onChange: (next: Filters) => void;
  onReset: () => void;
  accounts: Account[];
  categories: Category[];
  labels: Label[];
}) {
  // Local draft so typing doesn't fire a request per keystroke;
  // re-synced during render when the applied value changes (e.g. Reset)
  const [draft, setDraft] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (prevValue !== value) {
    setPrevValue(value);
    setDraft(value);
  }

  const set = <K extends keyof Filters>(key: K, val: Filters[K]) =>
    setDraft((d) => ({ ...d, [key]: val }));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onChange(draft);
      }}
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8"
    >
      <Field label="Account">
        <Select
          value={draft.account_id}
          onChange={(e) => set("account_id", e.target.value)}
        >
          <option value="">All</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Category">
        <Select
          value={draft.category_id}
          onChange={(e) => set("category_id", e.target.value)}
        >
          <option value="">All</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Type">
        <Select
          value={draft.classification}
          onChange={(e) =>
            set(
              "classification",
              e.target.value as TransactionClassification | "",
            )
          }
        >
          <option value="">All</option>
          {CLASSIFICATIONS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Merchant">
        <TextInput
          type="text"
          placeholder="Search merchant"
          value={draft.merchant}
          onChange={(e) => set("merchant", e.target.value)}
        />
      </Field>
      <LabelFilterField
        labels={labels}
        selected={draft.label_ids}
        onChange={(next) => set("label_ids", next)}
      />
      <Field label="From">
        <TextInput
          type="date"
          value={draft.start_date}
          onChange={(e) => set("start_date", e.target.value)}
        />
      </Field>
      <Field label="To">
        <TextInput
          type="date"
          value={draft.end_date}
          onChange={(e) => set("end_date", e.target.value)}
        />
      </Field>
      <Field label="Min amount">
        <TextInput
          type="number"
          step="0.01"
          placeholder="0.00"
          value={draft.min_amount}
          onChange={(e) => set("min_amount", e.target.value)}
        />
      </Field>
      <Field label="Max amount">
        <TextInput
          type="number"
          step="0.01"
          placeholder="0.00"
          value={draft.max_amount}
          onChange={(e) => set("max_amount", e.target.value)}
        />
      </Field>
      <Field label="Sort by">
        <Select
          value={draft.sort_by}
          onChange={(e) => set("sort_by", e.target.value as TransactionSortBy)}
        >
          <option value="transaction_date">Date</option>
          <option value="amount">Amount</option>
          <option value="merchant_name">Merchant</option>
        </Select>
      </Field>
      <Field label="Direction">
        <Select
          value={draft.sort_dir}
          onChange={(e) => set("sort_dir", e.target.value as SortDir)}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </Select>
      </Field>
      <div className="col-span-2 flex gap-2 sm:col-span-3 lg:col-span-4 xl:col-span-8">
        <Button type="submit">Apply filters</Button>
        <Button type="button" variant="ghost" onClick={onReset}>
          Reset
        </Button>
      </div>
    </form>
  );
}
