"use client";

import Link from "next/link";

import { MonthlySpendingChart } from "@/components/charts/MonthlySpendingChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SkeletonLines } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import {
  useAccounts,
  useMonthlySpending,
  useTransactions,
} from "@/lib/hooks";
import { formatDate, formatMoney, monthStart, toNumber } from "@/lib/format";
import { useRequiredUser } from "@/lib/user";

export default function DashboardPage() {
  const user = useRequiredUser();

  const accounts = useAccounts(user.id);
  const monthly = useMonthlySpending(user.id, { start_date: monthStart(5) });
  const recent = useTransactions({
    user_id: user.id,
    page: 1,
    page_size: 8,
  });

  const totalBalance = (accounts.data ?? []).reduce(
    (sum, a) => sum + toNumber(a.current_balance),
    0,
  );

  const currentMonthKey = monthStart(0).slice(0, 7);
  const thisMonth = monthly.data?.months.find(
    (m) => m.month === currentMonthKey,
  );
  // Backend convention: net = spending − income; flip so positive = saved.
  const savedThisMonth = thisMonth ? -toNumber(thisMonth.net) : 0;

  const hasAccounts = (accounts.data?.length ?? 0) > 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Your money at a glance"
        action={
          <Link href="/connect">
            <Button variant="secondary">Connect a bank</Button>
          </Link>
        }
      />

      {accounts.isError ? (
        <Card>
          <ErrorState error={accounts.error} onRetry={() => accounts.refetch()} />
        </Card>
      ) : !accounts.isPending && !hasAccounts ? (
        <Card>
          <EmptyState
            title="No accounts connected yet"
            hint="Connect a bank to pull in your accounts and transactions."
            action={
              <Link href="/connect">
                <Button>Connect a bank</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Total balance"
              value={formatMoney(totalBalance)}
              sub={`${accounts.data?.length ?? 0} accounts`}
              loading={accounts.isPending}
            />
            <StatTile
              label="Spending this month"
              value={formatMoney(thisMonth?.spending ?? 0)}
              loading={monthly.isPending}
            />
            <StatTile
              label="Income this month"
              value={formatMoney(thisMonth?.income ?? 0)}
              loading={monthly.isPending}
            />
            <StatTile
              label="Saved this month"
              value={formatMoney(savedThisMonth)}
              sub="income − spending"
              subTone={savedThisMonth >= 0 ? "good" : "bad"}
              loading={monthly.isPending}
            />
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader title="Spending vs income" subtitle="Last 6 months" />
              {monthly.isPending ? (
                <SkeletonLines lines={5} />
              ) : monthly.isError ? (
                <ErrorState
                  error={monthly.error}
                  onRetry={() => monthly.refetch()}
                  compact
                />
              ) : (
                <MonthlySpendingChart months={monthly.data.months} />
              )}
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader
                title="Recent transactions"
                action={
                  <Link
                    href="/transactions"
                    className="text-xs font-medium text-accent hover:underline"
                  >
                    View all
                  </Link>
                }
              />
              {recent.isPending ? (
                <SkeletonLines lines={6} />
              ) : recent.isError ? (
                <ErrorState
                  error={recent.error}
                  onRetry={() => recent.refetch()}
                  compact
                />
              ) : recent.data.items.length === 0 ? (
                <EmptyState
                  title="No transactions yet"
                  hint="Sync your accounts to pull in transactions."
                />
              ) : (
                <ul className="divide-y divide-line">
                  {recent.data.items.map((t) => (
                    <li
                      key={t.id}
                      className="flex items-center justify-between gap-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm text-ink">
                          {t.merchant_name ?? "Unknown merchant"}
                        </p>
                        <p className="mt-0.5 flex items-center gap-2 text-xs text-ink-3">
                          {formatDate(t.transaction_date)}
                          {t.pending && <Badge tone="warn">pending</Badge>}
                        </p>
                      </div>
                      <span
                        className={`shrink-0 text-sm font-medium tabular-nums ${
                          toNumber(t.amount) < 0 ? "text-good" : "text-ink"
                        }`}
                      >
                        {toNumber(t.amount) < 0 ? "+" : "−"}
                        {formatMoney(Math.abs(toNumber(t.amount)), t.currency)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </>
  );
}
