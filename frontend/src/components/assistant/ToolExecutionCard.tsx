"use client";

/**
 * Expandable "Tools used" trail under an assistant message. Shows only the
 * humanized tool name, status, and duration — never internals.
 */

import type { ToolCallSummary } from "@/lib/api/assistant";
import { Spinner } from "@/components/ui/Spinner";

function humanize(name: string): string {
  const words = name.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function StatusIcon({ status }: { status: ToolCallSummary["status"] }) {
  if (status === "running") return <Spinner size={12} />;
  if (status === "failed") {
    return (
      <span aria-label="Failed" className="text-bad">
        ✗
      </span>
    );
  }
  return (
    <span aria-label="Completed" className="text-good">
      ✓
    </span>
  );
}

export function ToolExecutionCard({ tools }: { tools: ToolCallSummary[] }) {
  if (tools.length === 0) return null;
  const running = tools.some((t) => t.status === "running");

  return (
    <details
      open={running}
      className="mt-2 rounded-lg border border-line bg-page text-xs"
    >
      <summary className="cursor-pointer select-none px-3 py-2 font-medium text-ink-3 hover:text-ink-2">
        Tools used ({tools.length})
      </summary>
      <ul className="space-y-1 border-t border-line px-3 py-2">
        {tools.map((tool, i) => (
          <li key={`${tool.name}-${i}`} className="flex items-center gap-2">
            <StatusIcon status={tool.status} />
            <span className="text-ink-2">{humanize(tool.name)}</span>
            {tool.status !== "running" && tool.duration_ms != null && (
              <span className="text-ink-3">
                {tool.status === "completed" ? "completed" : "failed"} in{" "}
                {tool.duration_ms}ms
              </span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
