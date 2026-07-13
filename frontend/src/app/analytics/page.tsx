"use client";

import { useState } from "react";

import { BarList } from "@/components/charts/BarList";
import { MonthlySpendingChart } from "@/components/charts/MonthlySpendingChart";
import { MonthOverMonthChart } from "@/components/charts/MonthOverMonthChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SkeletonLines } from "@/components/ui/Skeleton";
import {
  useCategoryBreakdown,
  useMonthlySpending,
  useMonthOverMonth,
  useTopMerchants,
} from "@/lib/hooks";
import { formatMoney, formatPercent, monthStart, toNumber } from "@/lib/format";
import { useRequiredUser } from "@/lib/user";

const RANGES = [
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "12 months", months: 12 },
] as const;

function RangePicker({
  value,
  onChange,
}: {
  value: number;
  onChange: (months: number) => void;
}) {
  return (
    <div className="flex rounded-lg border border-line bg-surface p-0.5">
      {RANGES.map((r) => (
        <button
          key={r.months}
          onClick={() => onChange(r.months)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            value === r.months
              ? "bg-accent/10 text-accent"
              : "text-ink-2 hover:text-ink"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const user = useRequiredUser();
  const [months, setMonths] = useState(6);

  const range = { start_date: monthStart(months - 1) };

  const monthly = useMonthlySpending(user.id, range);
  const breakdown = useCategoryBreakdown(user.id, range);
  const merchants = useTopMerchants(user.id, { ...range, limit: 10 });
  const mom = useMonthOverMonth(user.id, months);

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Spending patterns across your accounts"
        action={<RangePicker value={months} onChange={setMonths} />}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Spending vs income"
            subtitle={`Last ${months} months`}
          />
          {monthly.isPending ? (
            <SkeletonLines lines={5} />
          ) : monthly.isError ? (
            <ErrorState
              error={monthly.error}
              onRetry={() => monthly.refetch()}
              compact
            />
          ) : monthly.data.months.length === 0 ? (
            <EmptyState title="No data in this range" />
          ) : (
            <MonthlySpendingChart months={monthly.data.months} />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Spending trend"
            subtitle="Month over month, with change vs prior"
          />
          {mom.isPending ? (
            <SkeletonLines lines={5} />
          ) : mom.isError ? (
            <ErrorState error={mom.error} onRetry={() => mom.refetch()} compact />
          ) : mom.data.months.length === 0 ? (
            <EmptyState title="No data in this range" />
          ) : (
            <MonthOverMonthChart months={mom.data.months} />
          )}
        </Card>

        <Card>
          <CardHeader
            title="Spending by category"
            subtitle={
              breakdown.data
                ? `${formatMoney(breakdown.data.total_spending)} total`
                : undefined
            }
          />
          {breakdown.isPending ? (
            <SkeletonLines lines={6} />
          ) : breakdown.isError ? (
            <ErrorState
              error={breakdown.error}
              onRetry={() => breakdown.refetch()}
              compact
            />
          ) : breakdown.data.categories.length === 0 ? (
            <EmptyState title="No spending in this range" />
          ) : (
            <BarList
              items={breakdown.data.categories.map((c) => ({
                label: c.category_name,
                value: toNumber(c.total),
                detail: `${c.transaction_count} transactions · ${formatPercent(c.share_pct)} of spending`,
              }))}
            />
          )}
        </Card>

        <Card>
          <CardHeader title="Top merchants" subtitle="Ranked by total spend" />
          {merchants.isPending ? (
            <SkeletonLines lines={6} />
          ) : merchants.isError ? (
            <ErrorState
              error={merchants.error}
              onRetry={() => merchants.refetch()}
              compact
            />
          ) : merchants.data.merchants.length === 0 ? (
            <EmptyState title="No spending in this range" />
          ) : (
            <BarList
              items={merchants.data.merchants.map((m) => ({
                label: m.merchant_name,
                value: toNumber(m.total),
                detail: `${m.transaction_count} transactions`,
              }))}
            />
          )}
        </Card>
      </div>
    </>
  );
}
