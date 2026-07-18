"use client";

import { setThemePreference, useThemePreference, type ThemePreference } from "@/lib/theme";

const OPTIONS: { value: ThemePreference; label: string; icon: string }[] = [
  { value: "system", label: "System", icon: "◐" },
  { value: "light", label: "Light", icon: "☀" },
  { value: "dark", label: "Dark", icon: "☾" },
];

export function ThemeToggle() {
  const preference = useThemePreference();

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="flex gap-1 rounded-lg border border-line bg-page p-1"
    >
      {OPTIONS.map(({ value, label, icon }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setThemePreference(value)}
            className={`flex flex-1 items-center justify-center rounded-md py-1.5 text-sm transition-colors ${
              active
                ? "bg-surface text-ink shadow-sm"
                : "text-ink-3 hover:text-ink-2"
            }`}
          >
            <span aria-hidden>{icon}</span>
          </button>
        );
      })}
    </div>
  );
}
