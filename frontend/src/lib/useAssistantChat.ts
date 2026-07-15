"use client";

/**
 * Chat state for the AI assistant page.
 *
 * A reducer is the single source of truth for the transcript; React Query's
 * useMutation wraps each streamed exchange so in-flight state and retries
 * follow the app-wide pattern. Assistant messages hold a list of typed
 * parts so richer content (charts, tables) can be added as new part kinds
 * without reshaping the store.
 */

import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  streamMessage,
  type ChatRequest,
  type ToolCallSummary,
} from "./api/assistant";

export type MessagePart = { kind: "text"; text: string };
// future: | { kind: "chart"; ... } | { kind: "table"; ... }

export interface AssistantChatMessage {
  id: string;
  role: "user" | "assistant";
  parts: MessagePart[];
  /** Tool audit trail (assistant messages only). */
  tools: ToolCallSummary[];
  status: "streaming" | "done" | "error";
  errorDetail?: string;
}

interface ChatState {
  messages: AssistantChatMessage[];
  conversationId: string | null;
  /** Text of the last user message, kept for retry. */
  lastSent: string | null;
}

type Action =
  | { type: "exchange_started"; userText: string; assistantId: string }
  | { type: "token"; assistantId: string; text: string }
  | { type: "tool"; assistantId: string; tool: ToolCallSummary }
  | {
      type: "done";
      assistantId: string;
      conversationId: string;
      message: string;
      tools: ToolCallSummary[];
    }
  | { type: "error"; assistantId: string; detail: string }
  | { type: "retry_started"; assistantId: string }
  /** Stream over with no done/error (user pressed stop): settle the bubble. */
  | { type: "settled"; assistantId: string };

const initialState: ChatState = {
  messages: [],
  conversationId: null,
  lastSent: null,
};

function updateMessage(
  messages: AssistantChatMessage[],
  id: string,
  update: (message: AssistantChatMessage) => AssistantChatMessage,
): AssistantChatMessage[] {
  return messages.map((m) => (m.id === id ? update(m) : m));
}

function appendText(parts: MessagePart[], text: string): MessagePart[] {
  const last = parts[parts.length - 1];
  if (last?.kind === "text") {
    return [...parts.slice(0, -1), { kind: "text", text: last.text + text }];
  }
  return [...parts, { kind: "text", text }];
}

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "exchange_started":
      return {
        ...state,
        lastSent: action.userText,
        messages: [
          ...state.messages,
          {
            id: `user-${action.assistantId}`,
            role: "user",
            parts: [{ kind: "text", text: action.userText }],
            tools: [],
            status: "done",
          },
          {
            id: action.assistantId,
            role: "assistant",
            parts: [],
            tools: [],
            status: "streaming",
          },
        ],
      };
    case "token":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (m) => ({
          ...m,
          parts: appendText(m.parts, action.text),
        })),
      };
    case "tool":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (m) => {
          const existing = m.tools.findLast((t) => t.name === action.tool.name);
          const tools =
            existing && existing.status === "running"
              ? m.tools.map((t) => (t === existing ? action.tool : t))
              : [...m.tools, action.tool];
          return { ...m, tools };
        }),
      };
    case "done":
      return {
        ...state,
        conversationId: action.conversationId,
        messages: updateMessage(state.messages, action.assistantId, (m) => ({
          ...m,
          // trust the final text — it's what the backend persisted
          parts: [{ kind: "text", text: action.message }],
          tools: action.tools,
          status: "done",
        })),
      };
    case "error":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (m) => ({
          ...m,
          status: "error",
          errorDetail: action.detail,
        })),
      };
    case "retry_started":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (m) => ({
          ...m,
          parts: [],
          tools: [],
          status: "streaming",
          errorDetail: undefined,
        })),
      };
    case "settled":
      return {
        ...state,
        messages: updateMessage(state.messages, action.assistantId, (m) =>
          m.status !== "streaming"
            ? m
            : m.parts.length > 0
              ? { ...m, status: "done" }
              : { ...m, status: "error", errorDetail: "Response stopped." },
        ),
      };
  }
}

let nextId = 0;
function makeId(): string {
  nextId += 1;
  return `msg-${Date.now()}-${nextId}`;
}

export function useAssistantChat() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const mutation = useMutation({
    mutationFn: async ({
      request,
      assistantId,
    }: {
      request: ChatRequest;
      assistantId: string;
    }) => {
      const controller = new AbortController();
      abortRef.current = controller;
      await streamMessage(
        request,
        {
          onToken: (text) => dispatch({ type: "token", assistantId, text }),
          onTool: (tool) => dispatch({ type: "tool", assistantId, tool }),
          onDone: (done) =>
            dispatch({
              type: "done",
              assistantId,
              conversationId: done.conversation_id,
              message: done.message,
              tools: done.tool_calls,
            }),
          onError: (detail) => dispatch({ type: "error", assistantId, detail }),
        },
        controller.signal,
      );
      dispatch({ type: "settled", assistantId });
    },
  });

  const streaming = state.messages.some((m) => m.status === "streaming");

  const send = useCallback(
    (text: string) => {
      const message = text.trim();
      if (!message || streaming) return;
      const assistantId = makeId();
      dispatch({ type: "exchange_started", userText: message, assistantId });
      mutation.mutate({
        request: {
          conversation_id: state.conversationId,
          message,
        },
        assistantId,
      });
    },
    [mutation, state.conversationId, streaming],
  );

  /** Re-run the last exchange after an error, reusing its bubbles. */
  const retry = useCallback(() => {
    const failed = state.messages.findLast(
      (m) => m.role === "assistant" && m.status === "error",
    );
    if (!failed || !state.lastSent || streaming) return;
    dispatch({ type: "retry_started", assistantId: failed.id });
    mutation.mutate({
      request: {
        conversation_id: state.conversationId,
        message: state.lastSent,
      },
      assistantId: failed.id,
    });
  }, [mutation, state, streaming]);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return {
    messages: state.messages,
    conversationId: state.conversationId,
    streaming,
    send,
    retry,
    stop,
  };
}
