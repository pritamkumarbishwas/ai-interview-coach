import { api, toApiError } from "@/lib/api";
import type {
  CreateInvitationInput,
  Decision,
  IntegrityReport,
  Invitation,
  JobAnalytics,
  ReviewTimeline,
  Scorecard,
  ShadowReport,
  ShortlistEntry,
} from "@/types";

/** Recordings and exports can be large; allow the same headroom as an upload. */
const LARGE_RESPONSE_TIMEOUT_MS = 60_000;

export async function listInvitations(jobId: string): Promise<Invitation[]> {
  try {
    const { data } = await api.get<Invitation[]>("/invitations", {
      params: { job_id: jobId },
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createInvitation(
  input: CreateInvitationInput,
): Promise<Invitation> {
  try {
    const { data } = await api.post<Invitation>("/invitations", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function revokeInvitation(id: string): Promise<void> {
  try {
    await api.delete(`/invitations/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}

/** Sends a reminder and returns the invitation with a freshly rotated link. */
export async function remindInvitation(id: string): Promise<Invitation> {
  try {
    const { data } = await api.post<Invitation>(`/invitations/${id}/remind`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Grants extra round time (accessibility accommodation) on an invitation. */
export async function extendInvitation(
  id: string,
  minutes: number,
): Promise<Invitation> {
  try {
    const { data } = await api.post<Invitation>(`/invitations/${id}/extend`, {
      minutes,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Advisory integrity summary + flagged-moment timeline for a candidate. */
export async function getInvitationIntegrity(
  id: string,
): Promise<IntegrityReport> {
  try {
    const { data } = await api.get<IntegrityReport>(`/invitations/${id}/integrity`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Advisory, rubric-based competency scorecard with cited evidence. */
export async function getInvitationScorecard(id: string): Promise<Scorecard> {
  try {
    const { data } = await api.get<Scorecard>(`/invitations/${id}/scorecard`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Ranked, advisory shortlist for a job (score + integrity + decision). */
export async function getJobShortlist(jobId: string): Promise<ShortlistEntry[]> {
  try {
    const { data } = await api.get<ShortlistEntry[]>("/invitations/shortlist", {
      params: { job_id: jobId },
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Aggregate funnel + score/integrity distributions for a job (advisory). */
export async function getJobAnalytics(jobId: string): Promise<JobAnalytics> {
  try {
    const { data } = await api.get<JobAnalytics>("/invitations/analytics", {
      params: { job_id: jobId },
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** How often the advisory AI matched the decisions humans recorded (advisory). */
export async function getJobShadow(jobId: string): Promise<ShadowReport> {
  try {
    const { data } = await api.get<ShadowReport>("/invitations/shadow", {
      params: { job_id: jobId },
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Download a job's candidate rows as a CSV blob (caller revokes the URL). */
export async function downloadJobCandidatesCsv(jobId: string): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>("/invitations/export", {
      params: { job_id: jobId },
      responseType: "blob",
      timeout: LARGE_RESPONSE_TIMEOUT_MS,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Download a one-page PDF summary of a job's pipeline (caller revokes URL). */
export async function downloadJobCandidatesPdf(jobId: string): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>("/invitations/export.pdf", {
      params: { job_id: jobId },
      responseType: "blob",
      timeout: LARGE_RESPONSE_TIMEOUT_MS,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Record the human decision for a candidate (never set by the AI). */
export async function setInvitationDecision(
  id: string,
  decision: Decision,
  note = "",
): Promise<Invitation> {
  try {
    const { data } = await api.patch<Invitation>(`/invitations/${id}/decision`, {
      decision,
      note,
    });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Answers + integrity moments anchored to recording time (advisory). */
export async function getInvitationTimeline(
  id: string,
): Promise<ReviewTimeline> {
  try {
    const { data } = await api.get<ReviewTimeline>(`/invitations/${id}/timeline`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/**
 * Fetch a candidate's finalized recording as a blob. Callers should
 * `URL.createObjectURL` and revoke it on unmount.
 */
export async function getInvitationRecordingBlob(
  id: string,
  kind = "camera",
): Promise<Blob> {
  try {
    const { data } = await api.get<Blob>(
      `/invitations/${id}/recordings/${kind}`,
      { responseType: "blob", timeout: LARGE_RESPONSE_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
