"use client";

/**
 * Request a password-reset email. The backend answers 202 with the same
 * body whether or not the address exists, and this page reflects that.
 */

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");

  const submit = useMutation({
    mutationFn: () => api.forgotPassword(email.trim()),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate();
  };

  const error =
    submit.error instanceof ApiError
      ? submit.error.detail
      : submit.error instanceof Error
        ? submit.error.message
        : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4">
      <Card className="w-full max-w-md">
        <h1 className="text-lg font-semibold text-ink">Forgot your password?</h1>
        <p className="mt-1 text-sm text-ink-3">
          Enter your account email and we&apos;ll send a link to choose a new
          one.
        </p>

        {submit.isSuccess ? (
          <p className="mt-5 text-sm text-good">{submit.data.detail}</p>
        ) : (
          <form onSubmit={handleSubmit} className="mt-5 space-y-3">
            <Field label="Email">
              <TextInput
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </Field>
            {error && (
              <p role="alert" className="text-xs text-bad">
                {error}
              </p>
            )}
            <Button type="submit" loading={submit.isPending} className="w-full">
              Send reset link
            </Button>
          </form>
        )}

        <p className="mt-4 text-center text-xs text-ink-3">
          Remembered it?{" "}
          <Link
            href="/"
            className="text-accent underline-offset-2 hover:underline"
          >
            Back to sign in
          </Link>
        </p>
      </Card>
    </main>
  );
}
