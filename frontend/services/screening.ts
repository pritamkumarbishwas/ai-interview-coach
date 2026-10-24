import { api, toApiError } from "@/lib/api";
import type {
  AnswerResult,
  CurrentQuestion,
  InvitationSession,
  ScreeningConversation,
} from "@/types";

/**
 * Public candidate surface, addressed purely by the magic-link token. These
 * requests are deliberately unauthenticated: the token *is* the credential.
 */

/** LLM-backed endpoints need far more headroom than the default 30s. */
const LLM_TIMEOUT_MS = 120_000;
/** Chunked recording uploads and transcription of a full answer. */
const UPLOAD_TIMEOUT_MS = 60_000;

export async function getSession(token: string): Promise<InvitationSession> {
  try {
    const { data } = await api.get<InvitationSession>(`/screening/${token}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function startInterview(
  token: string,
  consent: boolean,
): Promise<CurrentQuestion> {
  try {
    const { data } = await api.post<CurrentQuestion>(
      `/screening/${token}/start`,
      { consent },
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getCurrentQuestion(
  token: string,
): Promise<CurrentQuestion> {
  try {
    // May finish a reserved start (LLM call) after a failed first attempt.
    const { data } = await api.get<CurrentQuestion>(
      `/screening/${token}/current-question`,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getConversation(
  token: string,
): Promise<ScreeningConversation> {
  try {
    const { data } = await api.get<ScreeningConversation>(
      `/screening/${token}/conversation`,
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function submitAnswer(
  token: string,
  questionId: string,
  answer: string,
): Promise<AnswerResult> {
  try {
    const { data } = await api.post<AnswerResult>(
      `/screening/${token}/questions/${questionId}/answer`,
      { answer },
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Upload one recorded session chunk (screen+camera composite) for a guest. */
export async function uploadRecordingChunk(
  token: string,
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
    await api.post(`/screening/${token}/recordings/chunk`, form, {
      timeout: UPLOAD_TIMEOUT_MS,
    });
  } catch (error) {
    throw toApiError(error);
  }
}

/** Record one advisory integrity signal (passive proctoring). Best-effort. */
export async function recordEvent(
  token: string,
  type: string,
  details: Record<string, unknown> = {},
): Promise<void> {
  try {
    await api.post(`/screening/${token}/proctoring/events`, { type, details });
  } catch (error) {
    // Integrity signals are advisory; never surface a failure to the candidate.
    console.warn("Could not record integrity signal", type, toApiError(error).message);
  }
}

/** Server-side speech-to-text for one recorded answer (Safari/Firefox path). */
export async function transcribeAnswer(
  token: string,
  audio: Blob,
  contentType = "audio/webm",
): Promise<string> {
  const baseContentType = contentType.split(";")[0].trim() || "audio/webm";
  const form = new FormData();
  form.append("content_type", baseContentType);
  form.append("audio", audio, "answer.webm");
  try {
    const { data } = await api.post<{ text: string }>(
      `/screening/${token}/transcribe`,
      form,
      { timeout: UPLOAD_TIMEOUT_MS },
    );
    return data.text;
  } catch (error) {
    throw toApiError(error);
  }
}
