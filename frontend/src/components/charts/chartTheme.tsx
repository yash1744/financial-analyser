"use client";

/**
 * Shared Recharts chrome. Colors come from the CSS custom properties defined
 * in globals.css so light/dark swap automatically.
 */

import type { ReactNode } from "react";

export const chart = {
  series1: "var(--series-1)", // blue — spending / primary
  series2: "var(--series-2)", // aqua — income
  grid: "var(--grid)",
  axis: "var(--ink-3)",
} as const;

export const axisTickStyle = { fill: "var(--ink-3)", fontSize: 11 };

export function TooltipFrame({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-sm">
      <p className="mb-1 text-xs font-medium text-ink">{title}</p>
      {children}
    </div>
  );
}

export function TooltipRow({
  swatch,
  label,
  value,
}: {
  swatch?: string;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {swatch && (
        <span
          aria-hidden
          className="h-2 w-2 rounded-sm"
          style={{ background: swatch }}
        />
      )}
      <span className="text-ink-2">{label}</span>
      <span className="ml-auto pl-4 font-medium text-ink tabular-nums">
        {value}
      </span>
    </div>
  );
}

export function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span
        aria-hidden
        className="h-2 w-2 rounded-sm"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}
