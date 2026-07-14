"use client";

const SUGGESTIONS = [
  "How much did I spend this month?",
  "Compare my spending with last month",
  "What are my recurring subscriptions?",
  "Where am I spending the most money?",
  "Show my biggest transactions",
];

export function SuggestedPrompts({
  onPick,
  disabled,
}: {
  onPick: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 py-8 text-center">
      <div>
        <p className="text-lg font-semibold text-ink">
          Ask about your finances
        </p>
        <p className="mt-1 text-sm text-ink-3">
          The assistant reads your synced accounts and transactions.
        </p>
      </div>
      <div className="grid w-full max-w-2xl gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            disabled={disabled}
            className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm text-ink-2 transition-colors hover:border-accent hover:text-ink disabled:opacity-60"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
