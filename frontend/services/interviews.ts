import { api, toApiError } from "@/lib/api";
import type {
  AnswerResult,
  CreateInterviewInput,
  CurrentQuestion,
  InterviewDetail,
  InterviewSummary,
  Question,
  Report,
} from "@/types";

/** LLM-backed endpoints need far more headroom than the default 30s. */
const LLM_TIMEOUT_MS = 120_000;

export async function listInterviews(): Promise<InterviewSummary[]> {
  try {
    const { data } = await api.get<InterviewSummary[]>("/interviews");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getInterview(id: string): Promise<InterviewDetail> {
  try {
    const { data } = await api.get<InterviewDetail>(`/interviews/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createInterview(
  input: CreateInterviewInput,
): Promise<InterviewDetail> {
  try {
    const { data } = await api.post<InterviewDetail>("/interviews", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Generates the first question (LLM) and marks the interview in_progress. */
export async function startInterview(id: string): Promise<CurrentQuestion> {
  try {
    const { data } = await api.post<CurrentQuestion>(
      `/interviews/${id}/start`,
      undefined,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getCurrentQuestion(
  id: string,
): Promise<CurrentQuestion> {
  try {
    const { data } = await api.get<CurrentQuestion>(
      `/interviews/${id}/current-question`,
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function submitAnswer(
  questionId: string,
  answer: string,
): Promise<AnswerResult> {
  try {
    const { data } = await api.post<AnswerResult>(
      `/questions/${questionId}/answer`,
      { answer },
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getReport(interviewId: string): Promise<Report> {
  try {
    const { data } = await api.get<Report>(
      `/interviews/${interviewId}/report`,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Find the question currently awaiting an answer (by id). */
export function findCurrentQuestion(
  interview: InterviewDetail,
): Question | null {
  if (!interview.current_question_id) return null;
  return (
    interview.questions.find((q) => q.id === interview.current_question_id) ??
    null
  );
}
