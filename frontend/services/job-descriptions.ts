import { api, toApiError } from "@/lib/api";
import type {
  CreateJobDescriptionInput,
  JobDescription,
  JobDescriptionSummary,
} from "@/types";

/** LLM-backed endpoints need far more headroom than the default 30s. */
const LLM_TIMEOUT_MS = 120_000;

export async function listJobDescriptions(): Promise<JobDescriptionSummary[]> {
  try {
    const { data } = await api.get<JobDescriptionSummary[]>("/job-descriptions");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getJobDescription(id: string): Promise<JobDescription> {
  try {
    const { data } = await api.get<JobDescription>(`/job-descriptions/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createJobDescription(
  input: CreateJobDescriptionInput,
): Promise<JobDescription> {
  try {
    const { data } = await api.post<JobDescription>(
      "/job-descriptions",
      input,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function deleteJobDescription(id: string): Promise<void> {
  try {
    await api.delete(`/job-descriptions/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}
