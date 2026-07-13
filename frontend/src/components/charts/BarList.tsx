"use client";

/**
 * Horizontal magnitude ranking as an HTML bar list (single sequential hue).
 * Labels and values stay in ink tokens; the bar alone carries magnitude.
 */

import { formatMoney } from "@/lib/format";

export interface BarListItem {
  label: string;
  value: number;
  /** e.g. "12 transactions · 34.2%" */
  detail?: string;
}

export function BarList({ items }: { items: BarListItem[] }) {
  const max = Math.max(...items.map((i) => i.value), 0);
  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate text-ink" title={item.label}>
              {item.label}
            </span>
            <span className="shrink-0 font-medium text-ink tabular-nums">
              {formatMoney(item.value)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-series-1"
                style={{ width: max > 0 ? `${(item.value / max) * 100}%` : 0 }}
              />
            </div>
          </div>
          {item.detail && (
            <p className="mt-0.5 text-xs text-ink-3">{item.detail}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
