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
  account_ids: string[];
  category_ids: string[];
  classifications: TransactionClassification[];
  merchant: string;
  label_ids: string[];
  start_date: string;
  end_date: string;
  min_amount: string;
  max_amount: string;
  sort_by: TransactionSortBy;
  sort_dir: SortDir;
}

interface MultiSelectOption {
  value: string;
  label: string;
}

/** Checkbox popover for filters that accept more than one value at once
 * (matches any of the selected values — OR). Selected values render as
 * removable chips below the trigger so the active set stays visible
 * without reopening the popover, plus a "Clear all" inside it. */
function MultiSelectField({
  fieldLabel,
  options,
  selected,
  onChange,
  emptyHint = "Nothing to select yet.",
}: {
  fieldLabel: string;
  options: MultiSelectOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  emptyHint?: string;
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

  const toggle = (value: string) =>
    onChange(
      selected.includes(value)
        ? selected.filter((s) => s !== value)
        : [...selected, value],
    );
  const remove = (value: string) =>
    onChange(selected.filter((s) => s !== value));

  const labelOf = (value: string) =>
    options.find((o) => o.value === value)?.label ?? value;

  return (
    <Field label={fieldLabel}>
      <div className="relative" ref={panelRef}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-left text-sm text-ink hover:border-ink-3"
        >
          {selected.length === 0 ? "All" : `${selected.length} selected`}
        </button>
        {open && (
          <div className="absolute left-0 top-full z-10 mt-1 w-52 rounded-lg border border-line bg-surface p-2 shadow-lg">
            {options.length === 0 ? (
              <p className="px-1 py-1 text-xs text-ink-3">{emptyHint}</p>
            ) : (
              <>
                {selected.length > 0 && (
                  <button
                    type="button"
                    onClick={() => onChange([])}
                    className="mb-1 px-1 text-xs text-ink-3 underline-offset-2 hover:text-accent hover:underline"
                  >
                    Clear all
                  </button>
                )}
                <div className="max-h-48 space-y-0.5 overflow-y-auto">
                  {options.map((option) => (
                    <label
                      key={option.value}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm text-ink hover:bg-line"
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(option.value)}
                        onChange={() => toggle(option.value)}
                        className="accent-accent"
                      />
                      <span className="truncate">{option.label}</span>
                    </label>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      {selected.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {selected.map((value) => (
            <span
              key={value}
              className="inline-flex items-center gap-1 rounded-full bg-line px-2 py-0.5 text-xs text-ink-2"
            >
              <span className="max-w-[8rem] truncate">{labelOf(value)}</span>
              <button
                type="button"
                onClick={() => remove(value)}
                aria-label={`Remove ${labelOf(value)}`}
                className="text-ink-3 hover:text-ink"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
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
      <MultiSelectField
        fieldLabel="Accounts"
        options={accounts.map((a) => ({ value: a.id, label: a.display_name }))}
        selected={draft.account_ids}
        onChange={(next) => set("account_ids", next)}
        emptyHint="No accounts yet."
      />
      <MultiSelectField
        fieldLabel="Categories"
        options={categories.map((c) => ({ value: c.id, label: c.name }))}
        selected={draft.category_ids}
        onChange={(next) => set("category_ids", next)}
        emptyHint="No categories yet."
      />
      <MultiSelectField
        fieldLabel="Type"
        options={CLASSIFICATIONS}
        selected={draft.classifications}
        onChange={(next) =>
          set("classifications", next as TransactionClassification[])
        }
      />
      <Field label="Merchant">
        <TextInput
          type="text"
          placeholder="Search merchant"
          value={draft.merchant}
          onChange={(e) => set("merchant", e.target.value)}
        />
      </Field>
      <MultiSelectField
        fieldLabel="Labels"
        options={labels.map((l) => ({ value: l.id, label: l.name }))}
        selected={draft.label_ids}
        onChange={(next) => set("label_ids", next)}
        emptyHint="No labels yet."
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
