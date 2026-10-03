import { Bot } from "lucide-react";

import { Avatar } from "@/components/ui/avatar";
import type { ChatMessage } from "@/data/mock";
import { cx } from "@/lib/utils";

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isAI = message.author === "ai";

  return (
    <li
      className={cx(
        "flex gap-3 animate-rise",
        isAI ? "" : "flex-row-reverse",
      )}
      aria-label={isAI ? "AI interviewer message" : "Your message"}
    >
      {isAI ? (
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-white">
          <Bot className="h-4 w-4" aria-hidden />
        </span>
      ) : (
        <Avatar name="You" size="sm" className="mt-0.5" />
      )}

      <div className={cx("min-w-0 max-w-[85%]", isAI ? "" : "text-right")}>
        <div
          className={cx(
            "rounded-2xl px-4 py-3 text-sm leading-relaxed",
            isAI
              ? "rounded-tl-md border border-[#f8dcb8] bg-ai text-ink"
              : "rounded-tr-md bg-mist text-ink",
          )}
        >
          {message.text}
        </div>
        <p className="mt-1 px-1 text-[11px] text-ink-3">
          {isAI ? "AI Interviewer" : "You"} · {message.time}
        </p>
      </div>
    </li>
  );
}
