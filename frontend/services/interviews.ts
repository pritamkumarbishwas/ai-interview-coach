import { api, toApiError } from "@/lib/api";
import type {
  AnswerResponse,
  CreateInterviewInput,
  Interview,
  Question,
  Report,
} from "@/types";

export async function listInterviews(): Promise<Interview[]> {
  try {
    const { data } = await api.get<Interview[]>("/interviews");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getInterview(id: string | number): Promise<Interview> {
  try {
    const { data } = await api.get<Interview>(`/interviews/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createInterview(
  input: CreateInterviewInput,
): Promise<Interview> {
  try {
    const { data } = await api.post<Interview>("/interviews", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function startInterview(id: string | number): Promise<Interview> {
  try {
    const { data } = await api.post<Interview>(`/interviews/${id}/start`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getCurrentQuestion(
  id: string | number,
): Promise<Question | null> {
  try {
    const { data } = await api.get<Question | null>(
      `/interviews/${id}/current-question`,
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function submitAnswer(
  questionId: string | number,
  answerText: string,
): Promise<AnswerResponse> {
  try {
    const { data } = await api.post<AnswerResponse>(
      `/questions/${questionId}/answer`,
      { answer_text: answerText },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getReport(
  interviewId: string | number,
): Promise<Report> {
  try {
    const { data } = await api.get<Report>(`/interviews/${interviewId}/report`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
