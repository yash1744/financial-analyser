"use client";

import { Button } from "@/components/ui/Button";
import type { AssistantChatMessage } from "@/lib/useAssistantChat";

import { Markdown } from "./Markdown";
import { StreamingIndicator } from "./StreamingIndicator";
import { ToolExecutionCard } from "./ToolExecutionCard";

export function AssistantMessage({
  message,
  onRetry,
}: {
  message: AssistantChatMessage;
  onRetry: () => void;
}) {
  const hasText = message.parts.some(
    (part) => part.kind === "text" && part.text.length > 0,
  );

  return (
    <div className="flex justify-start">
      <div className="max-w-[95%] rounded-2xl rounded-bl-sm border border-line bg-surface px-4 py-3 md:max-w-[85%]">
        {message.parts.map((part, i) =>
          part.kind === "text" ? <Markdown key={i} text={part.text} /> : null,
        )}

        {message.status === "streaming" && !hasText && (
          <div className="py-1">
            <StreamingIndicator />
          </div>
        )}

        {message.status === "error" && (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-bad">
              {message.errorDetail ?? "Something went wrong."}
            </p>
            <Button variant="secondary" className="px-3 py-1 text-xs" onClick={onRetry}>
              Retry
            </Button>
          </div>
        )}

        <ToolExecutionCard tools={message.tools} />
      </div>
    </div>
  );
}
