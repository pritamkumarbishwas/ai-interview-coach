"use client";

import { useEffect, useRef } from "react";

import { Bot } from "lucide-react";

import { ChatMessageBubble } from "@/components/interview/chat-message";
import type { ChatMessage } from "@/data/mock";

interface InterviewFeedProps {
  messages: ChatMessage[];
}

export function InterviewFeed({ messages }: InterviewFeedProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div
        className="flex min-h-[280px] flex-col items-center justify-center px-6 py-10 text-center"
        aria-label="Interview conversation"
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-brand">
          <Bot className="h-5 w-5" aria-hidden />
        </span>
        <p className="mt-3 text-sm font-medium text-ink">
          The conversation will appear here
        </p>
        <p className="mt-1 max-w-[260px] text-[13px] leading-relaxed text-ink-3">
          Once the interview starts, the AI asks the first question and you can
          reply below.
        </p>
      </div>
    );
  }

  return (
    <div
      className="hide-scrollbar max-h-[420px] min-h-[280px] space-y-4 overflow-y-auto px-4 py-4"
      aria-label="Interview conversation"
    >
      <ul className="space-y-4">
        {messages.map((message) => (
          <ChatMessageBubble key={message.id} message={message} />
        ))}
      </ul>
      <div ref={endRef} />
    </div>
  );
}
