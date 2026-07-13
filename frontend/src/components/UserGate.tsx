"use client";

/**
 * Blocks the app until a demo user exists (the backend has no auth yet).
 * Creates one via POST /users, or accepts an existing user id — the backend
 * has no lookup-by-email endpoint, so a returning user on a fresh browser
 * pastes the id shown when the user was created.
 */

import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "@/lib/api/client";
import { api } from "@/lib/api/endpoints";
import { useUser } from "@/lib/user";

import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { Field, TextInput } from "./ui/Field";
import { Spinner } from "./ui/Spinner";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function SetupForm() {
  const { setUser } = useUser();
  const [email, setEmail] = useState("");
  const [existingId, setExistingId] = useState("");
  const [idError, setIdError] = useState<string | null>(null);

  const createUser = useMutation({
    mutationFn: (value: string) => api.createUser(value),
    onSuccess: (user) => setUser({ id: user.id, email: user.email }),
  });

  const handleCreate = (e: FormEvent) => {
    e.preventDefault();
    createUser.mutate(email.trim());
  };

  const handleExisting = (e: FormEvent) => {
    e.preventDefault();
    const id = existingId.trim();
    if (!UUID_RE.test(id)) {
      setIdError("That doesn't look like a valid user id (UUID).");
      return;
    }
    setIdError(null);
    setUser({ id, email: email.trim() || "existing user" });
  };

  const createError =
    createUser.error instanceof ApiError && createUser.error.status === 409
      ? "A user with this email already exists. Paste its user id below instead."
      : createUser.error instanceof Error
        ? createUser.error.message
        : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4">
      <Card className="w-full max-w-md">
        <h1 className="text-lg font-semibold text-ink">Welcome</h1>
        <p className="mt-1 text-sm text-ink-3">
          The backend has no sign-in yet — create a demo user to get started.
        </p>

        <form onSubmit={handleCreate} className="mt-5 space-y-3">
          <Field label="Email">
            <TextInput
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </Field>
          {createError && (
            <p role="alert" className="text-xs text-bad">
              {createError}
            </p>
          )}
          <Button type="submit" loading={createUser.isPending} className="w-full">
            Create user
          </Button>
        </form>

        <div className="my-5 flex items-center gap-3 text-xs text-ink-3">
          <span className="h-px flex-1 bg-line" />
          or
          <span className="h-px flex-1 bg-line" />
        </div>

        <form onSubmit={handleExisting} className="space-y-3">
          <Field label="Existing user id">
            <TextInput
              value={existingId}
              onChange={(e) => setExistingId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          </Field>
          {idError && (
            <p role="alert" className="text-xs text-bad">
              {idError}
            </p>
          )}
          <Button type="submit" variant="secondary" className="w-full">
            Use existing user
          </Button>
        </form>
      </Card>
    </main>
  );
}

export function UserGate({ children }: { children: ReactNode }) {
  const { user, ready } = useUser();

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-page">
        <Spinner />
      </div>
    );
  }
  if (!user) return <SetupForm />;
  return <>{children}</>;
}
