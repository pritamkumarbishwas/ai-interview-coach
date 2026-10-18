import { api, toApiError } from "@/lib/api";
import type {
  AnswerResult,
  CurrentQuestion,
  InvitationSession,
} from "@/types";

/**
 * Public candidate surface, addressed purely by the magic-link token. These
 * requests are deliberately unauthenticated: the token *is* the credential.
 */

/** LLM-backed endpoints need far more headroom than the default 30s. */
const LLM_TIMEOUT_MS = 120_000;

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
    const { data } = await api.get<CurrentQuestion>(
      `/screening/${token}/current-question`,
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
