"use client";

/**
 * Landing page for the emailed verification link. Redeems the ?token=
 * automatically; on failure offers a resend (which needs a session).
 */

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";

function errorDetail(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function VerifyEmail() {
  const token = useSearchParams().get("token") ?? "";

  const confirm = useMutation({
    mutationFn: () => api.verifyEmail(token),
  });
  // useMutation identity changes per render; mutate on mount only
  const { mutate } = confirm;
  useEffect(() => {
    if (token) mutate();
  }, [token, mutate]);

  const resend = useMutation({
    mutationFn: () => api.resendVerification(),
  });

  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4">
      <Card className="w-full max-w-md text-center">
        <h1 className="text-lg font-semibold text-ink">Email verification</h1>

        {!token && (
          <p className="mt-3 text-sm text-bad">
            This link is missing its verification token. Open the link from
            your email again.
          </p>
        )}

        {token && confirm.isPending && (
          <div className="mt-4 flex justify-center">
            <Spinner />
          </div>
        )}

        {confirm.isSuccess && (
          <>
            <p className="mt-3 text-sm text-good">
              Your email address is verified.
            </p>
            <Link
              href="/"
              className="mt-4 inline-block text-sm text-accent underline-offset-2 hover:underline"
            >
              Go to the app
            </Link>
          </>
        )}

        {confirm.isError && (
          <div className="mt-3 space-y-3">
            <p className="text-sm text-bad">{errorDetail(confirm.error)}</p>
            <p className="text-xs text-ink-3">
              Links expire and can only be used once. Sign in, then request a
              fresh one:
            </p>
            <Button
              variant="secondary"
              loading={resend.isPending}
              onClick={() => resend.mutate()}
            >
              Resend verification email
            </Button>
            {resend.isSuccess && (
              <p className="text-xs text-good">{resend.data.detail}</p>
            )}
            {resend.isError && (
              <p className="text-xs text-bad">
                {errorDetail(resend.error)}
                {resend.error instanceof ApiError &&
                  resend.error.status === 401 && (
                    <>
                      {" "}
                      <Link
                        href="/"
                        className="text-accent underline-offset-2 hover:underline"
                      >
                        Sign in first.
                      </Link>
                    </>
                  )}
              </p>
            )}
          </div>
        )}
      </Card>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-page">
          <Spinner />
        </div>
      }
    >
      <VerifyEmail />
    </Suspense>
  );
}
