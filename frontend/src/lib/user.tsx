"use client";

/**
 * The backend has no auth yet — user_id rides in every request. This store
 * holds the demo user (created via POST /users) persisted in localStorage,
 * exposed to React via useSyncExternalStore.
 */

import {
  createContext,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const STORAGE_KEY = "finance.user";

export interface StoredUser {
  id: string;
  email: string;
}

// --- localStorage-backed external store ---

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener); // cross-tab changes
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

// Cache the parsed value so getSnapshot returns a stable reference
let cachedRaw: string | null = null;
let cachedUser: StoredUser | null = null;

function getSnapshot(): StoredUser | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === cachedRaw) return cachedUser;
  cachedRaw = raw;
  cachedUser = null;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as StoredUser;
      if (parsed.id && parsed.email) cachedUser = parsed;
    } catch {
      // corrupted storage — treat as signed out
    }
  }
  return cachedUser;
}

function getServerSnapshot(): StoredUser | null {
  return null;
}

function setStoredUser(user: StoredUser | null) {
  if (user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
  emit();
}

// --- context ---

interface UserContextValue {
  user: StoredUser | null;
  /** false during SSR/hydration, before localStorage has been read */
  ready: boolean;
  setUser: (user: StoredUser) => void;
  clearUser: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // false on the server render, true once hydrated on the client
  const ready = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  const value = useMemo(
    () => ({
      user,
      ready,
      setUser: setStoredUser,
      clearUser: () => setStoredUser(null),
    }),
    [user, ready],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
}

export function useUser(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be used within UserProvider");
  return ctx;
}

/** For pages that render only when a user exists (behind UserGate). */
export function useRequiredUser(): StoredUser {
  const { user } = useUser();
  if (!user) throw new Error("useRequiredUser called with no active user");
  return user;
}
