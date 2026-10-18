import { api, toApiError } from "@/lib/api";
import type { CreateInvitationInput, Invitation } from "@/types";

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
