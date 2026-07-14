import type { AssistantChatMessage } from "@/lib/useAssistantChat";

export function UserMessage({ message }: { message: AssistantChatMessage }) {
  const text = message.parts
    .map((part) => (part.kind === "text" ? part.text : ""))
    .join("");
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-sm leading-relaxed text-white md:max-w-[70%]">
        {text}
      </div>
    </div>
  );
}
