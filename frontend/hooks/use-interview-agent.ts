"use client";

import { useCallback, useEffect, useRef } from "react";

import { ApiError } from "@/lib/api";
import {
  createInterviewAgent,
  historyToMessages,
  isAgUiEnabled,
  submitAnswerWithAgent,
  type AgentHistoryMessage,
} from "@/services/interview-agent";
import type { AgUiInterviewSnapshot, AnswerResult } from "@/types";

interface UseInterviewAgentOptions {
  enabled: boolean;
  interviewId: string;
  history: AgentHistoryMessage[];
  /** Changes whenever the stored transcript changes, forcing a fresh seed. */
  historySignature: string;
}

interface CachedAgent {
  signature: string;
  agent: ReturnType<typeof createInterviewAgent>;
}

export function useInterviewAgent({
  enabled,
  interviewId,
  history,
  historySignature,
}: UseInterviewAgentOptions) {
  const historyRef = useRef(history);
  const agentRef = useRef<CachedAgent | null>(null);
  const signature = `${interviewId}:${historySignature}`;

  historyRef.current = history;

  useEffect(
    () => () => {
      agentRef.current?.agent.abortRun();
      agentRef.current = null;
    },
    [],
  );

  const getAgent = useCallback(() => {
    const cached = agentRef.current;
    if (cached?.signature === signature) return cached.agent;

    cached?.agent.abortRun();
    const agent = createInterviewAgent(interviewId);
    agent.threadId = interviewId;
    agent.messages = historyToMessages(historyRef.current);
    agentRef.current = { signature, agent };
    return agent;
  }, [interviewId, signature]);

  const submitAnswer = useCallback(
    async (
      questionId: string,
      answer: string,
      onSnapshot?: (snapshot: AgUiInterviewSnapshot) => void,
    ): Promise<AnswerResult> => {
      if (!enabled || !isAgUiEnabled()) {
        throw new ApiError(
          "AG-UI is not enabled.",
          501,
          "feature_unavailable",
        );
      }

      const agent = getAgent();
      try {
        return await submitAnswerWithAgent(
          agent,
          questionId,
          answer,
          onSnapshot,
        );
      } catch (error) {
        // A failed run leaves the optimistic user message on the agent. Force
        // a fresh seed so a retry (or the REST fallback) starts clean.
        if (agentRef.current?.agent === agent) agentRef.current = null;
        throw error;
      }
    },
    [enabled, getAgent],
  );

  return { submitAnswer };
}
