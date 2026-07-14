"use client";

import { useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";

export function ChatInput({
  onSend,
  onStop,
  streaming,
}: {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !streaming;

  const submit = () => {
    if (!canSend) return;
    onSend(value);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-xl border border-line bg-surface p-2">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about your spending, subscriptions, merchants…"
        rows={Math.min(4, Math.max(1, value.split("\n").length))}
        className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink outline-none placeholder:text-ink-3"
      />
      {streaming ? (
        <Button variant="secondary" onClick={onStop}>
          Stop
        </Button>
      ) : (
        <Button onClick={submit} disabled={!canSend}>
          Send
        </Button>
      )}
    </div>
  );
}
