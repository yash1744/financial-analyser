"use client";

/**
 * Theme preference: "system" (default — follows the OS via the
 * prefers-color-scheme media query in globals.css, zero JS involved) or an
 * explicit "light"/"dark" override, persisted to localStorage and applied
 * as a data-theme attribute on <html>.
 *
 * The inline script in app/layout.tsx applies a stored override before
 * first paint (see the Next.js "preventing flash before hydration" guide);
 * this store's getSnapshot reads the same localStorage key so the toggle
 * UI's initial render always agrees with what's already in the DOM.
 */

import { useSyncExternalStore } from "react";

export type ThemePreference = "system" | "light" | "dark";

const STORAGE_KEY = "finance.theme";

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" ? stored : "system";
}

// "system" on the server render — matches the DOM's default (no
// data-theme attribute) before the inline script or React ever runs.
function getServerSnapshot(): ThemePreference {
  return "system";
}

function apply(preference: ThemePreference) {
  if (preference === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", preference);
  }
}

export function setThemePreference(preference: ThemePreference) {
  if (preference === "system") {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, preference);
  }
  apply(preference);
  emit();
}

export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
