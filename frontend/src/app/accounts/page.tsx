"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SkeletonLines } from "@/components/ui/Skeleton";
import type { Account } from "@/lib/api/types";
import { useAccounts, useFullSync, useSetAccountNickname } from "@/lib/hooks";
import { formatMoney, toNumber } from "@/lib/format";
import { useRequiredUser } from "@/lib/user";

const nicknameInputClass =
  "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none";

function NicknameEditor({
  account,
  userId,
  onDone,
}: {
  account: Account;
  userId: string;
  onDone: () => void;
}) {
  const [value, setValue] = useState(account.nickname ?? "");
  const setNickname = useSetAccountNickname(userId);

  const save = (nickname: string | null) =>
    setNickname.mutate(
      { accountId: account.id, nickname },
      { onSuccess: onDone },
    );

  return (
    <div className="space-y-2">
      <input
        autoFocus
        className={nicknameInputClass}
        value={value}
        maxLength={100}
        placeholder={account.name}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save(value);
          if (e.key === "Escape") onDone();
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          className="px-3 py-1 text-xs"
          loading={setNickname.isPending}
          onClick={() => save(value)}
        >
          Save
        </Button>
        <Button
          variant="ghost"
          className="px-3 py-1 text-xs"
          onClick={onDone}
        >
          Cancel
        </Button>
        {account.nickname && (
          <Button
            variant="ghost"
            className="px-3 py-1 text-xs text-bad"
            onClick={() => save(null)}
          >
            Remove nickname
          </Button>
        )}
      </div>
      {setNickname.isError && (
        <p className="text-xs text-bad">Could not save. Try again.</p>
      )}
    </div>
  );
}

function AccountCard({ account, userId }: { account: Account; userId: string }) {
  const isCredit = account.account_type === "credit";
  const [editing, setEditing] = useState(false);
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {editing ? (
            <NicknameEditor
              account={account}
              userId={userId}
              onDone={() => setEditing(false)}
            />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-semibold text-ink">
                  {account.display_name}
                </p>
                <button
                  type="button"
                  onClick={() => setEditing(true)}
                  className="shrink-0 text-xs text-ink-3 underline-offset-2 hover:text-accent hover:underline"
                >
                  {account.nickname ? "Edit" : "Add nickname"}
                </button>
              </div>
              {/* show the original Plaid name as secondary text when a
                  nickname is overriding it */}
              <p className="mt-0.5 text-xs text-ink-3">
                {account.nickname
                  ? `${account.name} · ${account.account_subtype ?? account.account_type}`
                  : (account.account_subtype ?? account.account_type)}
              </p>
            </>
          )}
        </div>
        {!editing && (
          <Badge tone={isCredit ? "warn" : "good"}>{account.account_type}</Badge>
        )}
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
  const sync = useFullSync();

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
            <AccountCard key={a.id} account={a} userId={user.id} />
          ))}
        </div>
      )}
    </>
  );
}
