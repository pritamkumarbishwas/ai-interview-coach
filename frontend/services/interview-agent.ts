import { HttpAgent, type Message } from "@ag-ui/client";

import { API_URL, ApiError, getToken, toApiError } from "@/lib/api";
import type { AgUiInterviewSnapshot, AnswerResult } from "@/types";

/** Opt-in switch; the REST answer endpoint stays the default path. */
export const AGUI_ENABLED =
  process.env.NEXT_PUBLIC_AGUI_ENABLED === "true";

export function isAgUiEnabled(): boolean {
  return AGUI_ENABLED;
}

export interface AgentHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface AgentHttpError extends Error {
  status?: number;
  payload?: { detail?: string; code?: string };
}

function newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function createInterviewAgent(interviewId: string): HttpAgent {
  const token = getToken();
  return new HttpAgent({
    url: `${API_URL.replace(/\/$/, "")}/agui/interviews/${interviewId}`,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export function historyToMessages(
  history: AgentHistoryMessage[],
): Message[] {
  return history.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
  }));
}

function toAgentApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  const candidate = error as AgentHttpError;
  if (typeof candidate?.status === "number") {
    const detail =
      typeof candidate.payload?.detail === "string"
        ? candidate.payload.detail
        : candidate.message || "AG-UI request failed";
    return new ApiError(
      detail,
      candidate.status,
      candidate.payload?.code ?? "error",
    );
  }
  return toApiError(error);
}

function statusForRunError(code: string | null | undefined): number {
  switch (code) {
    case "unauthenticated":
      return 401;
    case "conflict":
      return 409;
    case "feature_unavailable":
      return 501;
    case "service_unavailable":
      return 503;
    default:
      return 0;
  }
}

/**
 * Run one AG-UI answer turn on a seeded agent. The returned result is the same
 * shape as the REST answer endpoint, so callers can share their state updates.
 */
export async function submitAnswerWithAgent(
  agent: HttpAgent,
  questionId: string,
  answer: string,
  onSnapshot?: (snapshot: AgUiInterviewSnapshot) => void,
): Promise<AnswerResult> {
  agent.addMessage({
    id: newId("c"),
    role: "user",
    content: answer,
  });

  let result: AnswerResult | null = null;
  let runError: { message: string; code?: string | null } | null = null;

  try {
    const run = await agent.runAgent(
      {
        runId: newId("run"),
        forwardedProps: { question_id: questionId },
      },
      {
        onStateSnapshotEvent: ({ event }) => {
          onSnapshot?.(event.snapshot as AgUiInterviewSnapshot);
        },
        onRunFinishedEvent: (params) => {
          if (params.outcome === "success" && params.result) {
            result = params.result as AnswerResult;
          }
        },
        onRunErrorEvent: ({ event }) => {
          runError = { message: event.message, code: event.code };
        },
      },
    );

    if (runError) {
      const failure: { message: string; code?: string | null } = runError;
      throw new ApiError(
        failure.message,
        statusForRunError(failure.code),
        failure.code ?? "agui_error",
      );
    }

    const finalResult =
      result ??
      ("result" in run ? (run.result as AnswerResult | undefined) : undefined);
    if (!finalResult) {
      throw new ApiError(
        "AG-UI finished without an answer result.",
        0,
        "invalid_response",
      );
    }
    return finalResult;
  } catch (error) {
    throw toAgentApiError(error);
  }
}
