"use client";

import { ApiError } from "@/lib/api/client";

import { Button } from "./Button";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.plaidErrorCode === "ITEM_LOGIN_REQUIRED") {
      return "This bank connection needs to be re-authenticated. Reconnect it from the Connect Bank page.";
    }
    return error.detail;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function ErrorState({
  error,
  onRetry,
  compact = false,
}: {
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-3 text-center ${
        compact ? "py-4" : "py-10"
      }`}
    >
      <p className="text-sm font-medium text-bad">{messageFor(error)}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
