import { api, toApiError } from "@/lib/api";
import type { Resume, ResumeSummary, ResumeUploadResponse } from "@/types";

/** LLM-backed endpoints need far more headroom than the default 30s. */
export const LLM_TIMEOUT_MS = 120_000;

export async function listResumes(): Promise<ResumeSummary[]> {
  try {
    const { data } = await api.get<ResumeSummary[]>("/resumes");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getResume(id: string): Promise<Resume> {
  try {
    const { data } = await api.get<Resume>(`/resumes/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function uploadResume(
  file: File,
): Promise<ResumeUploadResponse> {
  try {
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header: the browser must add the multipart boundary.
    const { data } = await api.post<ResumeUploadResponse>(
      "/resumes/upload",
      form,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function deleteResume(id: string): Promise<void> {
  try {
    await api.delete(`/resumes/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}
