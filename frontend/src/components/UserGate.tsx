"use client";

/**
 * Blocks the app until a session exists. Register or sign in with
 * email + password; the backend returns a JWT that rides every request.
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

type Mode = "login" | "register";

function AuthForm() {
  const { setSession } = useUser();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      mode === "login"
        ? api.login(email.trim(), password)
        : api.register(email.trim(), password),
    onSuccess: (auth) =>
      setSession({
        token: auth.access_token,
        user: { id: auth.user.id, email: auth.user.email },
      }),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit.mutate();
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    submit.reset();
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
        <h1 className="text-lg font-semibold text-ink">
          {mode === "login" ? "Sign in" : "Create your account"}
        </h1>
        <p className="mt-1 text-sm text-ink-3">
          {mode === "login"
            ? "Welcome back — your data is waiting."
            : "Register with an email and a password of at least 8 characters."}
        </p>

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
          <Field label="Password">
            <TextInput
              type="password"
              required
              minLength={mode === "register" ? 8 : 1}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </Field>
          {error && (
            <p role="alert" className="text-xs text-bad">
              {error}
            </p>
          )}
          <Button type="submit" loading={submit.isPending} className="w-full">
            {mode === "login" ? "Sign in" : "Register"}
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-ink-3">
          {mode === "login" ? (
            <>
              New here?{" "}
              <button
                type="button"
                onClick={() => switchMode("register")}
                className="text-accent underline-offset-2 hover:underline"
              >
                Create an account
              </button>
            </>
          ) : (
            <>
              Already registered?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="text-accent underline-offset-2 hover:underline"
              >
                Sign in
              </button>
            </>
          )}
        </p>
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
  if (!user) return <AuthForm />;
  return <>{children}</>;
}
