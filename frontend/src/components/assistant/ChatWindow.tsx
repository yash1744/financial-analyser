"use client";

import { useAssistantChat } from "@/lib/useAssistantChat";

import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import { SuggestedPrompts } from "./SuggestedPrompts";

export function ChatWindow({ userId }: { userId: string }) {
  const { messages, streaming, send, retry, stop } = useAssistantChat(userId);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {messages.length === 0 ? (
        <SuggestedPrompts onPick={send} disabled={streaming} />
      ) : (
        <MessageList messages={messages} onRetry={retry} />
      )}
      <ChatInput onSend={send} onStop={stop} streaming={streaming} />
    </div>
  );
}
