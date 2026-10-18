import type { BadgeTone } from "@/components/ui/badge";
import type {
  Difficulty,
  IntegrityLevel,
  IntegrityPolicy,
  InterviewType,
  JobStatus,
  ProctoringMode,
  ResponseMode,
  Role,
  RoundConfig,
  TemplateConfig,
} from "@/types";
import { TYPE_LABELS } from "@/lib/interview";

/** Stable role sets for guards (module-level so effect deps stay constant). */
export const STAFF_ROLES: Role[] = ["admin", "recruiter", "reviewer"];
export const ADMIN_ROLES: Role[] = ["admin"];

export const ROLE_LABELS: Record<Role, string> = {
  candidate: "Candidate",
  admin: "Administrator",
  recruiter: "Recruiter",
  reviewer: "Reviewer",
};

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  draft: "Draft",
  open: "Open",
  closed: "Closed",
};

export const JOB_STATUS_TONES: Record<JobStatus, BadgeTone> = {
  draft: "muted",
  open: "success",
  closed: "neutral",
};

export const PROCTORING_LABELS: Record<ProctoringMode, string> = {
  off: "Off",
  camera_only: "Camera only",
  strict: "Strict",
};

export const INTEGRITY_LABELS: Record<IntegrityPolicy, string> = {
  advisory: "Advisory",
  strict: "Strict",
};

/** Advisory integrity *level* (session outcome) labels + tones. */
export const INTEGRITY_LEVEL_LABELS: Record<IntegrityLevel, string> = {
  low: "Low concern",
  moderate: "Moderate",
  elevated: "Elevated",
  high: "High",
};

export const INTEGRITY_LEVEL_TONES: Record<IntegrityLevel, BadgeTone> = {
  low: "success",
  moderate: "warning",
  elevated: "danger",
  high: "danger",
};

export const RESPONSE_MODE_LABELS: Record<ResponseMode, string> = {
  voice: "Voice",
  typed: "Typed",
  code: "Code editor",
  whiteboard: "Whiteboard",
};

export const RESPONSE_MODES: ResponseMode[] = [
  "voice",
  "typed",
  "code",
  "whiteboard",
];

export const INTERVIEW_TYPES = Object.keys(TYPE_LABELS) as InterviewType[];
export const DIFFICULTIES: Difficulty[] = [
  "beginner",
  "intermediate",
  "advanced",
];

export function newRound(index: number): RoundConfig {
  const key = index === 0 ? "screen" : `round-${index + 1}`;
  return {
    key,
    label: index === 0 ? "Screening" : `Round ${index + 1}`,
    interview_type: "technical",
    difficulty: "intermediate",
    duration_minutes: 30,
    target_questions: 5,
    response_modes: ["voice", "typed"],
  };
}

export function defaultTemplateConfig(): TemplateConfig {
  return {
    proctoring_mode: "strict",
    integrity_policy: "advisory",
    allow_pauses: false,
    rounds: [newRound(0)],
  };
}
