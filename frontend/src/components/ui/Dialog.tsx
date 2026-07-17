"use client";

/**
 * Thin styling wrapper around Radix's Dialog primitive. Radix owns the
 * hard parts a hand-rolled overlay tends to get wrong: focus trap, focus
 * restoration to the trigger on close, Escape handling, outside-click,
 * background scroll lock, and ARIA wiring (role="dialog", aria-modal,
 * label/description association) — this file only supplies classes from
 * the app's existing design tokens (bg-surface, border-line, text-ink, ...),
 * it doesn't reimplement any of Radix's behavior.
 */

import * as RadixDialog from "@radix-ui/react-dialog";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

export const Dialog = RadixDialog.Root;

export function DialogContent({
  children,
  className = "",
  ...props
}: ComponentPropsWithoutRef<typeof RadixDialog.Content>) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
      <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-8">
        <RadixDialog.Content
          className={`my-auto w-full max-w-2xl rounded-xl border border-line bg-surface shadow-xl focus:outline-none ${className}`}
          {...props}
        >
          {children}
        </RadixDialog.Content>
      </div>
    </RadixDialog.Portal>
  );
}

export function DialogTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <RadixDialog.Title className={`text-base font-semibold text-ink ${className}`}>
      {children}
    </RadixDialog.Title>
  );
}

/** Radix warns in dev if a Content has no accessible description; use this
 * when the visible header already conveys everything (nothing extra to
 * announce), so screen readers aren't handed a redundant description. */
export function DialogDescription({ children }: { children: ReactNode }) {
  return <RadixDialog.Description className="sr-only">{children}</RadixDialog.Description>;
}

export const DialogClose = RadixDialog.Close;
