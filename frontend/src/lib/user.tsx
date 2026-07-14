"use client";

/**
 * Signed-in user profile store. The JWT itself lives in an httpOnly
 * cookie set by the backend — JavaScript can never read it; the browser
 * attaches it to same-origin requests automatically. localStorage holds
 * only the non-sensitive profile (id + email) for display and cache
 * keying. A 401 from the API clears the profile, which re-renders the
 * login gate.
 */

import {
  createContext,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

const STORAGE_KEY = "finance.profile";
// pre-cookie stores; cleared on any write so stale tokens don't linger
const LEGACY_KEYS = ["finance.user", "finance.session"];

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

export function setProfile(user: StoredUser | null) {
  if (user) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
  LEGACY_KEYS.forEach((key) => localStorage.removeItem(key));
  emit();
}

/** Called by the api client when the backend rejects the cookie/token. */
export function clearSession() {
  setProfile(null);
}

// --- context ---

interface UserContextValue {
  user: StoredUser | null;
  /** false during SSR/hydration, before localStorage has been read */
  ready: boolean;
  setProfile: (user: StoredUser) => void;
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
      setProfile,
      clearUser: () => setProfile(null),
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
