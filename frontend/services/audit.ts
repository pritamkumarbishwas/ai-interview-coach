import { api, toApiError } from "@/lib/api";
import type { AuditLog } from "@/types";

export async function listAuditLogs(): Promise<AuditLog[]> {
  try {
    const { data } = await api.get<AuditLog[]>("/audit-logs");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
