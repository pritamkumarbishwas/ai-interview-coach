import { api, toApiError } from "@/lib/api";
import type { DashboardStats } from "@/types";

export async function getDashboardStats(): Promise<DashboardStats> {
  try {
    const { data } = await api.get<DashboardStats>("/dashboard/stats");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
