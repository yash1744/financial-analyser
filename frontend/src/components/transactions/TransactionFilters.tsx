"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import type {
  Account,
  Category,
  SortDir,
  TransactionClassification,
  TransactionSortBy,
} from "@/lib/api/types";

export interface Filters {
  account_id: string;
  category_id: string;
  classification: TransactionClassification | "";
  start_date: string;
  end_date: string;
  min_amount: string;
  max_amount: string;
  sort_by: TransactionSortBy;
  sort_dir: SortDir;
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
}: {
  value: Filters;
  onChange: (next: Filters) => void;
  onReset: () => void;
  accounts: Account[];
  categories: Category[];
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
              {a.name}
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
