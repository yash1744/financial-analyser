"use client";

/** Single-series spending trend; tooltip carries the delta vs prior month. */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MonthOverMonthPoint } from "@/lib/api/types";
import {
  formatMoney,
  formatMoneyCompact,
  formatMonth,
  toNumber,
} from "@/lib/format";

import { axisTickStyle, chart, TooltipFrame, TooltipRow } from "./chartTheme";

interface Row {
  month: string;
  spending: number;
  change: number | null;
  change_pct: number | null;
}

function MomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const delta =
    row.change === null
      ? "—"
      : `${row.change >= 0 ? "+" : ""}${formatMoney(row.change)}${
          row.change_pct !== null ? ` (${row.change_pct.toFixed(1)}%)` : ""
        }`;
  return (
    <TooltipFrame title={formatMonth(row.month)}>
      <div className="space-y-1">
        <TooltipRow
          swatch={chart.series1}
          label="Spending"
          value={formatMoney(row.spending)}
        />
        <TooltipRow label="vs prior" value={delta} />
      </div>
    </TooltipFrame>
  );
}

export function MonthOverMonthChart({
  months,
}: {
  months: MonthOverMonthPoint[];
}) {
  const data: Row[] = months.map((m) => ({
    month: m.month,
    spending: toNumber(m.spending),
    change: m.change === null ? null : toNumber(m.change),
    change_pct: m.change_pct,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
        <CartesianGrid stroke={chart.grid} strokeWidth={1} vertical={false} />
        <XAxis
          dataKey="month"
          tickFormatter={formatMonth}
          tick={axisTickStyle}
          axisLine={{ stroke: chart.grid }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v: number) => formatMoneyCompact(v)}
          tick={axisTickStyle}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip
          content={<MomTooltip />}
          cursor={{ stroke: "var(--ink-3)", strokeDasharray: "3 3" }}
        />
        <Line
          type="monotone"
          dataKey="spending"
          stroke={chart.series1}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, fill: chart.series1, stroke: "var(--surface)", strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
