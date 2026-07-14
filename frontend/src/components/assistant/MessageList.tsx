"use client";

/**
 * Scrollable transcript. Auto-scrolls to new content only while the user
 * is already near the bottom — scrolling up to reread pauses following.
 */

import { useEffect, useRef } from "react";

import type { AssistantChatMessage } from "@/lib/useAssistantChat";

import { MessageBubble } from "./MessageBubble";

const NEAR_BOTTOM_PX = 120;

export function MessageList({
  messages,
  onRetry,
}: {
  messages: AssistantChatMessage[];
  onRetry: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    followRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  useEffect(() => {
    const el = containerRef.current;
    if (el && followRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 space-y-4 overflow-y-auto py-4 pr-1"
    >
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onRetry={onRetry} />
      ))}
    </div>
  );
}
