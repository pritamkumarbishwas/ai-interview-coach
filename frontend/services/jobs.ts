import { api, toApiError } from "@/lib/api";
import type { CreateJobInput, Job, JobSummary, UpdateJobInput } from "@/types";

export async function listJobs(): Promise<JobSummary[]> {
  try {
    const { data } = await api.get<JobSummary[]>("/jobs");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getJob(id: string): Promise<Job> {
  try {
    const { data } = await api.get<Job>(`/jobs/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createJob(input: CreateJobInput): Promise<Job> {
  try {
    const { data } = await api.post<Job>("/jobs", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function updateJob(id: string, input: UpdateJobInput): Promise<Job> {
  try {
    const { data } = await api.patch<Job>(`/jobs/${id}`, input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function deleteJob(id: string): Promise<void> {
  try {
    await api.delete(`/jobs/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}

/** Replace the reviewers assigned to a requisition (recruiter/admin only). */
export async function setJobReviewers(id: string, reviewerIds: string[]): Promise<Job> {
  try {
    const { data } = await api.put<Job>(`/jobs/${id}/reviewers`, {
      reviewer_ids: reviewerIds,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
