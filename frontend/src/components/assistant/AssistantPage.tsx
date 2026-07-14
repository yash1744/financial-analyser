"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { useRequiredUser } from "@/lib/user";

import { ChatWindow } from "./ChatWindow";

export function AssistantPage() {
  const user = useRequiredUser();

  return (
    // fill the viewport under AppShell's padding so the input stays pinned:
    // mobile has the sticky top bar (~3rem) plus main's py-6
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col md:h-[calc(100dvh-4rem)]">
      <PageHeader
        title="AI Assistant"
        subtitle="Ask questions about your accounts, spending, and subscriptions"
      />
      <ChatWindow userId={user.id} />
    </div>
  );
}
