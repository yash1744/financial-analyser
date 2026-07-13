"use client";

/** Grouped bars: spending (blue) vs income (aqua) per calendar month. */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MonthlySpendingPoint } from "@/lib/api/types";
import {
  formatMoney,
  formatMoneyCompact,
  formatMonth,
  toNumber,
} from "@/lib/format";

import {
  axisTickStyle,
  chart,
  LegendSwatch,
  TooltipFrame,
  TooltipRow,
} from "./chartTheme";

interface Row {
  month: string;
  spending: number;
  income: number;
  net: number;
}

function MonthlyTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <TooltipFrame title={formatMonth(row.month)}>
      <div className="space-y-1">
        <TooltipRow
          swatch={chart.series1}
          label="Spending"
          value={formatMoney(row.spending)}
        />
        <TooltipRow
          swatch={chart.series2}
          label="Income"
          value={formatMoney(row.income)}
        />
        <TooltipRow label="Net" value={formatMoney(row.net)} />
      </div>
    </TooltipFrame>
  );
}

export function MonthlySpendingChart({
  months,
}: {
  months: MonthlySpendingPoint[];
}) {
  const data: Row[] = months.map((m) => ({
    month: m.month,
    spending: toNumber(m.spending),
    income: toNumber(m.income),
    net: toNumber(m.net),
  }));

  return (
    <div>
      <div className="mb-2 flex gap-4">
        <LegendSwatch color={chart.series1} label="Spending" />
        <LegendSwatch color={chart.series2} label="Income" />
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }} barGap={2}>
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
            content={<MonthlyTooltip />}
            cursor={{ fill: "var(--line)" }}
          />
          <Bar
            dataKey="spending"
            fill={chart.series1}
            radius={[4, 4, 0, 0]}
            maxBarSize={28}
            isAnimationActive={false}
          />
          <Bar
            dataKey="income"
            fill={chart.series2}
            radius={[4, 4, 0, 0]}
            maxBarSize={28}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
