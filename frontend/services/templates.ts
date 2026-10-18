import { api, toApiError } from "@/lib/api";
import type {
  CreateTemplateInput,
  InterviewTemplate,
  TemplatePreview,
  TemplatePreviewInput,
  TemplateSummary,
  UpdateTemplateInput,
} from "@/types";

/** Question generation is LLM-backed and needs generous headroom. */
const LLM_TIMEOUT_MS = 120_000;

export async function listTemplates(): Promise<TemplateSummary[]> {
  try {
    const { data } = await api.get<TemplateSummary[]>("/templates");
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getTemplate(id: string): Promise<InterviewTemplate> {
  try {
    const { data } = await api.get<InterviewTemplate>(`/templates/${id}`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function createTemplate(
  input: CreateTemplateInput,
): Promise<InterviewTemplate> {
  try {
    const { data } = await api.post<InterviewTemplate>("/templates", input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function updateTemplate(
  id: string,
  input: UpdateTemplateInput,
): Promise<InterviewTemplate> {
  try {
    const { data } = await api.patch<InterviewTemplate>(`/templates/${id}`, input);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function deleteTemplate(id: string): Promise<void> {
  try {
    await api.delete(`/templates/${id}`);
  } catch (error) {
    throw toApiError(error);
  }
}

export async function previewTemplateQuestion(
  id: string,
  input: TemplatePreviewInput,
): Promise<TemplatePreview> {
  try {
    const { data } = await api.post<TemplatePreview>(
      `/templates/${id}/preview`,
      input,
      { timeout: LLM_TIMEOUT_MS },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
