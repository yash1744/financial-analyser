"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { api } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import type { TransactionsSyncResponse } from "@/lib/api/types";
import { useQueryClient } from "@tanstack/react-query";
import { useRequiredUser } from "@/lib/user";

type Step =
  | { name: "idle" }
  | { name: "creating-token" }
  | { name: "link-open" }
  | { name: "exchanging" }
  | { name: "syncing"; institution: string | null }
  | { name: "done"; institution: string | null; added: number }
  | { name: "already-connected"; message: string }
  | { name: "error"; error: unknown };

/** Mounts only once we have a token; opens Plaid Link as soon as it's ready. */
function PlaidLinkLauncher({
  token,
  onSuccess,
  onExit,
}: {
  token: string;
  onSuccess: (publicToken: string) => void;
  onExit: () => void;
}) {
  const { open, ready } = usePlaidLink({
    token,
    onSuccess: (publicToken) => onSuccess(publicToken),
    onExit: () => onExit(),
  });

  useEffect(() => {
    if (ready) open();
  }, [ready, open]);

  return null;
}

export default function ConnectPage() {
  const user = useRequiredUser();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>({ name: "idle" });
  const [linkToken, setLinkToken] = useState<string | null>(null);

  const start = useCallback(async () => {
    setStep({ name: "creating-token" });
    try {
      const { link_token } = await api.createLinkToken(user.id);
      setLinkToken(link_token);
      setStep({ name: "link-open" });
    } catch (error) {
      setStep({ name: "error", error });
    }
  }, [user.id]);

  const handleLinkSuccess = useCallback(
    async (publicToken: string) => {
      setLinkToken(null);
      setStep({ name: "exchanging" });
      try {
        const item = await api.exchangePublicToken(user.id, publicToken);
        setStep({ name: "syncing", institution: item.institution_name });
        await api.syncAccounts(user.id, item.id);
        const txns: TransactionsSyncResponse = await api.syncTransactions(
          user.id,
          item.id,
        );
        queryClient.invalidateQueries();
        setStep({
          name: "done",
          institution: item.institution_name,
          added: txns.items.reduce((n, i) => n + i.added, 0),
        });
      } catch (error) {
        // duplicate connection: expected outcome, not a failure
        if (error instanceof ApiError && error.status === 409) {
          setStep({ name: "already-connected", message: error.detail });
        } else {
          setStep({ name: "error", error });
        }
      }
    },
    [user.id, queryClient],
  );

  const handleLinkExit = useCallback(() => {
    setLinkToken(null);
    setStep({ name: "idle" });
  }, []);

  const busy =
    step.name === "creating-token" ||
    step.name === "link-open" ||
    step.name === "exchanging" ||
    step.name === "syncing";

  return (
    <>
      <PageHeader
        title="Connect Bank"
        subtitle="Link an institution through Plaid to import accounts and transactions"
      />

      <div className="mx-auto max-w-xl">
        <Card>
          <CardHeader
            title="Add a bank connection"
            subtitle="Your credentials go to Plaid, never to this app. Sandbox institutions work with user_good / pass_good."
          />

          {step.name === "done" ? (
            <div className="space-y-4 py-2 text-center">
              <p className="text-sm text-ink">
                Connected{" "}
                <span className="font-semibold">
                  {step.institution ?? "your bank"}
                </span>{" "}
                and imported {step.added} transactions.
              </p>
              <div className="flex justify-center gap-2">
                <Link href="/">
                  <Button>Go to dashboard</Button>
                </Link>
                <Button variant="secondary" onClick={start}>
                  Connect another
                </Button>
              </div>
            </div>
          ) : step.name === "already-connected" ? (
            <div className="space-y-4 py-2 text-center">
              <p className="text-sm text-ink">{step.message}.</p>
              <p className="text-xs text-ink-3">
                No duplicate was created — your existing connection and its
                transactions are untouched. Use sync on the Accounts page to
                refresh its data.
              </p>
              <div className="flex justify-center gap-2">
                <Link href="/accounts">
                  <Button>View accounts</Button>
                </Link>
                <Button variant="secondary" onClick={start}>
                  Connect a different bank
                </Button>
              </div>
            </div>
          ) : step.name === "error" ? (
            <ErrorState error={step.error} onRetry={start} />
          ) : (
            <div className="space-y-4 py-2">
              {busy && (
                <div className="flex items-center gap-3 rounded-lg border border-line px-4 py-3 text-sm text-ink-2">
                  <Spinner size={16} />
                  {step.name === "creating-token" &&
                    "Preparing the secure Link session…"}
                  {step.name === "link-open" &&
                    "Complete the connection in the Plaid window…"}
                  {step.name === "exchanging" && "Finalizing the connection…"}
                  {step.name === "syncing" &&
                    `Importing accounts and transactions${
                      step.institution ? ` from ${step.institution}` : ""
                    }…`}
                </div>
              )}
              <Button onClick={start} loading={busy} className="w-full">
                Connect a bank
              </Button>
            </div>
          )}
        </Card>

        <Card className="mt-4">
          <CardHeader title="How it works" />
          <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-2">
            <li>We ask the backend for a short-lived Plaid Link token.</li>
            <li>You sign in to your bank inside Plaid&apos;s secure window.</li>
            <li>
              The backend exchanges the result for an encrypted connection —
              access tokens never touch the browser.
            </li>
            <li>Accounts and transactions sync automatically.</li>
          </ol>
        </Card>
      </div>

      {linkToken && (
        <PlaidLinkLauncher
          token={linkToken}
          onSuccess={handleLinkSuccess}
          onExit={handleLinkExit}
        />
      )}
    </>
  );
}
