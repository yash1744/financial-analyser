/**
 * AI assistant API: one-shot chat + SSE streaming.
 *
 * The streaming endpoint is POST, which EventSource can't do, so
 * streamMessage() parses the SSE frames off a fetch ReadableStream.
 * Stream-level problems are reported through the callbacks (never thrown)
 * so callers have exactly one error path.
 */

import { apiPost } from "./client";

export type ToolStatus = "running" | "completed" | "failed";

export interface ToolCallSummary {
  name: string;
  status: ToolStatus;
  duration_ms?: number | null;
}

export interface ChatRequest {
  user_id: string;
  conversation_id?: string | null;
  message: string;
}

export interface ChatResponse {
  conversation_id: string;
  message: string;
  tool_calls: ToolCallSummary[];
}

export interface ChatDone {
  conversation_id: string;
  message: string;
  tool_calls: ToolCallSummary[];
}

export interface StreamCallbacks {
  onToken: (text: string) => void;
  onTool: (tool: ToolCallSummary) => void;
  onDone: (done: ChatDone) => void;
  /** Backend `error` events, network failures, and disconnects all land here. */
  onError: (detail: string) => void;
}

/** One-shot fallback: full tool loop server-side, single JSON response. */
export function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  return apiPost<ChatResponse>("/ai/chat", request);
}

interface SseFrame {
  event: string;
  data: string;
}

/** Split complete `event:`/`data:` frames off the front of the buffer. */
function drainFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const frames: SseFrame[] = [];
  let rest = buffer;
  for (;;) {
    const boundary = rest.indexOf("\n\n");
    if (boundary === -1) break;
    const raw = rest.slice(0, boundary);
    rest = rest.slice(boundary + 2);
    let event = "message";
    const data: string[] = [];
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (data.length > 0) frames.push({ event, data: data.join("\n") });
  }
  return { frames, rest };
}

/**
 * Stream one exchange. Resolves when the stream closes; all outcomes
 * (including errors) are delivered via callbacks first.
 */
export async function streamMessage(
  request: ChatRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/v1/ai/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if ((error as Error).name !== "AbortError") {
      callbacks.onError("Cannot reach the API. Is the backend running?");
    }
    return;
  }

  if (!response.ok || !response.body) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON body; keep the generic message
    }
    callbacks.onError(detail);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const handle = ({ event, data }: SseFrame) => {
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      return; // malformed frame — ignore
    }
    const body = payload as Record<string, unknown>;
    switch (event) {
      case "token":
        callbacks.onToken(String(body.text ?? ""));
        break;
      case "tool":
        callbacks.onTool(body as unknown as ToolCallSummary);
        break;
      case "done":
        finished = true;
        callbacks.onDone(body as unknown as ChatDone);
        break;
      case "error":
        finished = true;
        callbacks.onError(String(body.detail ?? "Something went wrong."));
        break;
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = drainFrames(buffer);
      buffer = rest;
      frames.forEach(handle);
    }
  } catch (error) {
    if ((error as Error).name === "AbortError") return;
    if (!finished) callbacks.onError("The connection was interrupted.");
    return;
  }

  // stream closed cleanly but the exchange never concluded
  if (!finished) callbacks.onError("The response ended unexpectedly.");
}
