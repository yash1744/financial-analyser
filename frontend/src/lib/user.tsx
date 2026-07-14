"use client";

/**
 * Auth session store: JWT + user info persisted in localStorage, exposed
 * to React via useSyncExternalStore. The token rides every API request as
 * an Authorization header (see lib/api/client.ts); a 401 clears the
 * session, which re-renders the login gate.
 */

import {
  createContext,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const STORAGE_KEY = "finance.session";
const LEGACY_KEY = "finance.user"; // pre-auth store; cleared on load

export interface StoredUser {
  id: string;
  email: string;
}

export interface Session {
  token: string;
  user: StoredUser;
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
let cachedSession: Session | null = null;

function getSnapshot(): Session | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  cachedSession = null;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as Session;
      if (parsed.token && parsed.user?.id && parsed.user?.email) {
        cachedSession = parsed;
      }
    } catch {
      // corrupted storage — treat as signed out
    }
  }
  return cachedSession;
}

function getServerSnapshot(): Session | null {
  return null;
}

export function setSession(session: Session | null) {
  if (session) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
  localStorage.removeItem(LEGACY_KEY);
  emit();
}

/** Token for the api client (non-React access). */
export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return getSnapshot()?.token ?? null;
}

/** Called by the api client when the backend rejects the token. */
export function clearSession() {
  setSession(null);
}

// --- context ---

interface UserContextValue {
  user: StoredUser | null;
  /** false during SSR/hydration, before localStorage has been read */
  ready: boolean;
  setSession: (session: Session) => void;
  clearUser: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: ReactNode }) {
  const session = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // false on the server render, true once hydrated on the client
  const ready = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  const value = useMemo(
    () => ({
      user: session?.user ?? null,
      ready,
      setSession,
      clearUser: () => setSession(null),
    }),
    [session, ready],
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
