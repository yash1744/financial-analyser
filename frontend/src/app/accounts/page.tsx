"use client";

import Link from "next/link";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SkeletonLines } from "@/components/ui/Skeleton";
import type { Account } from "@/lib/api/types";
import { useAccounts, useFullSync } from "@/lib/hooks";
import { formatMoney, toNumber } from "@/lib/format";
import { useRequiredUser } from "@/lib/user";

function AccountCard({ account }: { account: Account }) {
  const isCredit = account.account_type === "credit";
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">
            {account.name}
          </p>
          <p className="mt-0.5 text-xs text-ink-3">
            {account.account_subtype ?? account.account_type}
          </p>
        </div>
        <Badge tone={isCredit ? "warn" : "good"}>{account.account_type}</Badge>
      </div>
      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-3">
            {isCredit ? "Balance owed" : "Current balance"}
          </p>
          <p className="mt-0.5 text-xl font-semibold text-ink">
            {account.current_balance === null
              ? "—"
              : formatMoney(account.current_balance, account.currency)}
          </p>
        </div>
        {account.available_balance !== null && (
          <div className="text-right">
            <p className="text-xs text-ink-3">Available</p>
            <p className="mt-0.5 text-sm font-medium text-ink-2">
              {formatMoney(account.available_balance, account.currency)}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function AccountsPage() {
  const user = useRequiredUser();
  const accounts = useAccounts(user.id);
  const sync = useFullSync(user.id);

  const total = (accounts.data ?? []).reduce(
    (sum, a) => sum + toNumber(a.current_balance),
    0,
  );

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle={
          accounts.data
            ? `${accounts.data.length} accounts · ${formatMoney(total)} total`
            : undefined
        }
        action={
          <Button
            variant="secondary"
            loading={sync.isPending}
            onClick={() => sync.mutate(undefined)}
          >
            {sync.isPending ? "Syncing…" : "Sync now"}
          </Button>
        }
      />

      {sync.isError && (
        <Card className="mb-4">
          <ErrorState error={sync.error} compact />
        </Card>
      )}
      {sync.isSuccess && (
        <p className="mb-4 text-sm text-good" role="status">
          Sync complete —{" "}
          {sync.data.transactions.items.reduce((n, i) => n + i.added, 0)} new
          transactions across {sync.data.accounts.items.length} connection(s).
        </p>
      )}

      {accounts.isPending ? (
        <Card>
          <SkeletonLines lines={6} />
        </Card>
      ) : accounts.isError ? (
        <Card>
          <ErrorState
            error={accounts.error}
            onRetry={() => accounts.refetch()}
          />
        </Card>
      ) : accounts.data.length === 0 ? (
        <Card>
          <EmptyState
            title="No accounts yet"
            hint="Connect a bank to pull in your accounts."
            action={
              <Link href="/connect">
                <Button>Connect a bank</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {accounts.data.map((a) => (
            <AccountCard key={a.id} account={a} />
          ))}
        </div>
      )}
    </>
  );
}
