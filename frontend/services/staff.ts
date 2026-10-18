import { api, setToken, toApiError } from "@/lib/api";
import type {
  AcceptStaffInvitationInput,
  CreateStaffInvitationInput,
  Role,
  StaffInvitation,
  TokenResponse,
  User,
} from "@/types";

export async function listStaff(): Promise<User[]> {
  try {
    const { data } = await api.get<User[]>("/staff/users");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function listStaffInvitations(): Promise<StaffInvitation[]> {
  try {
    const { data } = await api.get<StaffInvitation[]>("/staff/invitations");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createStaffInvitation(
  input: CreateStaffInvitationInput,
): Promise<StaffInvitation> {
  try {
    const { data } = await api.post<StaffInvitation>("/staff/invitations", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function revokeStaffInvitation(id: string): Promise<void> {
  try {
    await api.delete(`/staff/invitations/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}

export async function updateStaffRole(id: string, role: Role): Promise<User> {
  try {
    const { data } = await api.patch<User>(`/staff/users/${id}/role`, { role });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** Public: an invited staff member sets name/password and is logged in. */
export async function acceptStaffInvitation(
  input: AcceptStaffInvitationInput,
): Promise<TokenResponse> {
  try {
    const { data } = await api.post<TokenResponse>(
      "/staff/invitations/accept",
      input,
    );
    setToken(data.access_token);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
