import { api, toApiError } from "@/lib/api";
import type {
  Resume,
  ResumeActionResponse,
  ResumeAnalysisStatus,
  ResumeSummary,
  ResumeTextResponse,
  ResumeUploadResponse,
} from "@/types";

/** LLM-backed endpoints need far more headroom than the default 30s. */
export const LLM_TIMEOUT_MS = 120_000;
export const RESUME_POLL_MS = 2_000;
export const RESUME_POLL_TIMEOUT_MS = 180_000;

export function isResumeProcessing(status: ResumeAnalysisStatus): boolean {
  return status === "pending" || status === "processing";
}

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

export async function getResumeText(id: string): Promise<ResumeTextResponse> {
  try {
    const { data } = await api.get<ResumeTextResponse>(`/resumes/${id}/text`);
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

function filenameFromDisposition(
  header: string | undefined,
  fallback: string,
): string {
  if (!header) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      // Fall through to the plain filename.
    }
  }
  return /filename="?([^";]+)"?/i.exec(header)?.[1] ?? fallback;
}

export async function downloadResumeFile(
  id: string,
  fallbackName = "resume.pdf",
): Promise<{ blob: Blob; filename: string }> {
  try {
    const { data, headers } = await api.get<Blob>(`/resumes/${id}/file`, {
      responseType: "blob",
      timeout: LLM_TIMEOUT_MS,
    });
    return {
      blob: data,
      filename: filenameFromDisposition(
        headers["content-disposition"],
        fallbackName,
      ),
    };
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getResumePreview(
  id: string,
  page: number,
): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>(`/resumes/${id}/preview/${page}`, {
      responseType: "blob",
      timeout: LLM_TIMEOUT_MS,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function retryResumeAnalysis(
  id: string,
): Promise<ResumeActionResponse> {
  try {
    const { data } = await api.post<ResumeActionResponse>(
      `/resumes/${id}/analyze`,
      undefined,
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll until the worker has finished analysing the resume. */
export async function waitForResume(
  id: string,
  timeoutMs = RESUME_POLL_TIMEOUT_MS,
): Promise<Resume> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const resume = await getResume(id);
    if (!isResumeProcessing(resume.analysis.status)) return resume;
    await delay(RESUME_POLL_MS);
  }
  throw new Error(
    "Resume processing is taking longer than expected. Try again from My Resumes.",
  );
}
