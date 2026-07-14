"use client";

import type { AssistantChatMessage } from "@/lib/useAssistantChat";

import { AssistantMessage } from "./AssistantMessage";
import { UserMessage } from "./UserMessage";

export function MessageBubble({
  message,
  onRetry,
}: {
  message: AssistantChatMessage;
  onRetry: () => void;
}) {
  return message.role === "user" ? (
    <UserMessage message={message} />
  ) : (
    <AssistantMessage message={message} onRetry={onRetry} />
  );
}
