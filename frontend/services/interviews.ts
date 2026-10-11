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
/** Recording chunks can be large; give uploads generous headroom. */
const UPLOAD_TIMEOUT_MS = 60_000;

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

/** Records proctoring consent; required before start when mode != "off". */
export async function recordProctoringConsent(
  id: string,
  consent: boolean,
): Promise<void> {
  try {
    await api.post(`/interviews/${id}/proctoring/consent`, { consent });
  } catch (error) {
    throw toApiError(error);
  }
}

/** Records one proctoring event (e.g. camera_off, tab_blur) during a session. */
export async function recordProctoringEvent(
  id: string,
  type: string,
  details: Record<string, unknown> = {},
): Promise<void> {
  try {
    await api.post(`/interviews/${id}/proctoring/events`, { type, details });
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

/** Upload one recorded chunk for the given interview + kind. */
export async function uploadRecordingChunk(
  interviewId: string,
  kind: "camera" | "screen",
  seq: number,
  chunk: Blob,
  finalize: boolean,
  contentType = "video/webm",
): Promise<void> {
  const form = new FormData();
  form.append("kind", kind);
  form.append("seq", String(seq));
  form.append("finalize", String(finalize));
  form.append("content_type", contentType);
  form.append("chunk", chunk, `${kind}-${seq}.webm`);
  try {
    await api.post(`/interviews/${interviewId}/recordings/chunk`, form, {
      timeout: UPLOAD_TIMEOUT_MS,
    });
  } catch (error) {
    throw toApiError(error);
  }
}

/**
 * Fetch a finalized recording as a blob (authenticated via the axios
 * interceptor). Callers should `URL.createObjectURL` and revoke on unmount.
 */
export async function getRecordingBlob(
  interviewId: string,
  kind: "camera" | "screen",
): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>(
      `/interviews/${interviewId}/recordings/${kind}`,
      { responseType: "blob", timeout: UPLOAD_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Convenience: which recording kinds are present on an interview. */
export function recordingKinds(
  interview: InterviewDetail,
): ("camera" | "screen")[] {
  const kinds: ("camera" | "screen")[] = [];
  if (interview.recordings?.camera?.finalized) kinds.push("camera");
  if (interview.recordings?.screen?.finalized) kinds.push("screen");
  return kinds;
}
