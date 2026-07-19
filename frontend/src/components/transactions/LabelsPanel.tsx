"use client";

/**
 * Labels section for a transaction: assigned labels as removable chips,
 * plus a combobox to add an existing label or create a new one inline
 * (per issue #47 — "without leaving the transaction workflow"). Reads
 * through useTransactionDetail rather than the row it was opened from,
 * so it stays correct even if the row's own cached copy is stale.
 */

import { useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api/client";
import type { Label } from "@/lib/api/types";
import {
  useLabelAssignment,
  useLabelManagement,
  useLabels,
  useTransactionDetail,
} from "@/lib/hooks";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function LabelsPanel({ transactionId }: { transactionId: string }) {
  const detail = useTransactionDetail(transactionId);
  const allLabels = useLabels();
  const { assign, unassign } = useLabelAssignment(transactionId);
  const { createLabel } = useLabelManagement();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (detail.isPending) {
    return (
      <div className="flex justify-center py-4">
        <Spinner />
      </div>
    );
  }

  const assigned = detail.data?.labels ?? [];
  const assignedIds = new Set(assigned.map((l) => l.id));
  const trimmed = query.trim().toLowerCase();
  const candidates = (allLabels.data ?? []).filter(
    (l) => !assignedIds.has(l.id) && l.name.toLowerCase().includes(trimmed),
  );
  const exactMatch = (allLabels.data ?? []).some(
    (l) => l.name.toLowerCase() === trimmed,
  );

  const pick = (label: Label) => {
    assign.mutate(label.id);
    setQuery("");
  };

  const createAndAssign = () => {
    const name = query.trim();
    if (!name) return;
    createLabel.mutate(name, {
      onSuccess: (label) => {
        assign.mutate(label.id);
        setQuery("");
      },
    });
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {assigned.map((label) => (
          <span
            key={label.id}
            className="inline-flex items-center gap-1 rounded-full bg-line px-2 py-0.5 text-xs font-medium text-ink-2"
          >
            {label.name}
            <button
              type="button"
              onClick={() => unassign.mutate(label.id)}
              aria-label={`Remove ${label.name}`}
              className="text-ink-3 hover:text-bad"
            >
              ×
            </button>
          </span>
        ))}

        <div className="relative" ref={panelRef}>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="rounded-full border border-dashed border-line px-2 py-0.5 text-xs text-ink-3 hover:border-ink-3 hover:text-ink"
          >
            + Add label
          </button>
          {open && (
            <div className="absolute left-0 top-full z-10 mt-1 w-56 rounded-lg border border-line bg-surface p-2 shadow-lg">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search or create…"
                className="mb-2 w-full rounded-md border border-line bg-page px-2 py-1 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && query.trim() && !exactMatch) {
                    createAndAssign();
                  }
                }}
              />
              <div className="max-h-40 space-y-0.5 overflow-y-auto">
                {candidates.map((label) => (
                  <button
                    key={label.id}
                    type="button"
                    onClick={() => pick(label)}
                    className="block w-full truncate rounded-md px-2 py-1 text-left text-sm text-ink hover:bg-line"
                  >
                    {label.name}
                  </button>
                ))}
                {query.trim() && !exactMatch && (
                  <button
                    type="button"
                    onClick={createAndAssign}
                    className="block w-full truncate rounded-md px-2 py-1 text-left text-sm text-accent hover:bg-line"
                  >
                    Create “{query.trim()}”
                  </button>
                )}
                {candidates.length === 0 && !query.trim() && (
                  <p className="px-2 py-1 text-xs text-ink-3">
                    No other labels yet — type to create one.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {(assign.isError || unassign.isError || createLabel.isError) && (
        <p className="text-xs text-bad">
          {errorText(assign.error ?? unassign.error ?? createLabel.error)}
        </p>
      )}
    </div>
  );
}
