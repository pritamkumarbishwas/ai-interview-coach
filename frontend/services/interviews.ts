import { API_URL, api, toApiError } from "@/lib/api";
import type {
  AnswerResult,
  CreateInterviewInput,
  CurrentQuestion,
  InterviewDetail,
  InterviewResults,
  InterviewSummary,
  Question,
  RecordingPlaybackUrl,
  Report,
  ResultsSort,
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

/** Completed interviews plus server-side score stats, across all results. */
export async function getResults(
  sort: ResultsSort = "recent",
): Promise<InterviewResults> {
  try {
    const { data } = await api.get<InterviewResults>("/interviews/results", {
      params: { sort },
    });
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

/** Discards an unfinished interview (completed reports are retained). */
export async function deleteInterview(id: string): Promise<void> {
  try {
    await api.delete(`/interviews/${id}`);
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

/** Finish an in-progress interview early and start report generation. */
export async function completeInterview(id: string): Promise<InterviewDetail> {
  try {
    const { data } = await api.post<InterviewDetail>(
      `/interviews/${id}/complete`,
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

const reportRequests = new Map<string, Promise<Report>>();

export function getReport(interviewId: string): Promise<Report> {
  const inFlight = reportRequests.get(interviewId);
  if (inFlight) return inFlight;

  const request = fetchReport(interviewId);
  reportRequests.set(interviewId, request);
  void request
    .finally(() => {
      if (reportRequests.get(interviewId) === request) {
        reportRequests.delete(interviewId);
      }
    })
    .catch(() => {
      /* The caller handles the original rejection. */
    });
  return request;
}

async function fetchReport(interviewId: string): Promise<Report> {
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

/** Upload one recorded chunk of the session (screen+camera composite). */
export async function uploadRecordingChunk(
  interviewId: string,
  seq: number,
  chunk: Blob,
  finalize: boolean,
  contentType = "video/webm",
  captureStartedAtMs?: number,
): Promise<void> {
  // MediaRecorder blobs carry codec parameters (e.g. "video/webm;codecs=vp9,opus");
  // the API expects the bare MIME type.
  const baseContentType = contentType.split(";")[0].trim() || "video/webm";
  const form = new FormData();
  form.append("kind", "camera");
  form.append("seq", String(seq));
  form.append("finalize", String(finalize));
  form.append("content_type", baseContentType);
  if (captureStartedAtMs) {
    // Anchors reviewer-timeline offsets to media time 0.
    form.append("capture_started_at", new Date(captureStartedAtMs).toISOString());
  }
  form.append("chunk", chunk, `camera-${seq}.webm`);
  try {
    await api.post(`/interviews/${interviewId}/recordings/chunk`, form, {
      timeout: UPLOAD_TIMEOUT_MS,
    });
  } catch (error) {
    throw toApiError(error);
  }
}

/**
 * Mint a short-lived signed URL for the finalized recording. `<video>` cannot
 * attach the bearer header, so playback must use this URL instead of a blob.
 */
export async function getRecordingPlaybackUrl(
  interviewId: string,
): Promise<RecordingPlaybackUrl> {
  try {
    const { data } = await api.post<{
      path: string;
      expires_at: string;
      expires_in: number;
    }>(`/interviews/${interviewId}/recordings/camera/playback-url`);
    const base = API_URL.replace(/\/$/, "");
    return { ...data, url: `${base}${data.path}` };
  } catch (error) {
    throw toApiError(error);
  }
}

/** Server-side speech-to-text for one recorded answer. */
export async function transcribeAnswer(
  interviewId: string,
  audio: Blob,
): Promise<string> {
  const form = new FormData();
  form.append("content_type", audio.type.split(";")[0] || "audio/webm");
  form.append("audio", audio, "answer.webm");
  try {
    const { data } = await api.post<{ text: string }>(
      `/interviews/${interviewId}/transcribe`,
      form,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data.text;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Whether a finalized, non-empty session recording is present. */
export function hasSessionRecording(interview: InterviewDetail): boolean {
  const recording = interview.recordings?.camera;
  return Boolean(recording?.finalized && recording.size_bytes > 0);
}
