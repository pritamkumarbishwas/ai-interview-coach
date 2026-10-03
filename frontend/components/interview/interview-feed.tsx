"use client";

import { useEffect, useRef } from "react";

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
