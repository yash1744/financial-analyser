"use client";

/**
 * Landing page for the emailed password-reset link: pick a new password
 * for the ?token= carried in the URL.
 */

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";

function ResetPassword() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mismatch, setMismatch] = useState(false);

  const submit = useMutation({
    mutationFn: () => api.resetPassword(token, password),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirmation) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    submit.mutate();
  };

  const error = mismatch
    ? "Passwords don't match."
    : submit.error instanceof ApiError
      ? submit.error.detail
      : submit.error instanceof Error
        ? submit.error.message
        : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4">
      <Card className="w-full max-w-md">
        <h1 className="text-lg font-semibold text-ink">Choose a new password</h1>

        {!token ? (
          <p className="mt-3 text-sm text-bad">
            This link is missing its reset token. Open the link from your
            email again, or{" "}
            <Link
              href="/forgot-password"
              className="text-accent underline-offset-2 hover:underline"
            >
              request a new one
            </Link>
            .
          </p>
        ) : submit.isSuccess ? (
          <>
            <p className="mt-3 text-sm text-good">{submit.data.detail}</p>
            <Link
              href="/"
              className="mt-4 inline-block text-sm text-accent underline-offset-2 hover:underline"
            >
              Sign in
            </Link>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="mt-5 space-y-3">
            <Field label="New password">
              <TextInput
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </Field>
            <Field label="Confirm new password">
              <TextInput
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                placeholder="••••••••"
              />
            </Field>
            {error && (
              <p role="alert" className="text-xs text-bad">
                {error}
              </p>
            )}
            <Button type="submit" loading={submit.isPending} className="w-full">
              Reset password
            </Button>
          </form>
        )}
      </Card>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-page">
          <Spinner />
        </div>
      }
    >
      <ResetPassword />
    </Suspense>
  );
}
