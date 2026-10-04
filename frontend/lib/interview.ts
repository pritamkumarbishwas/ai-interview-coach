import type {
  BadgeTone,
} from "@/components/ui/badge";
import type {
  Difficulty,
  ExperienceLevel,
  InterviewStatus,
  InterviewType,
} from "@/types";

/** Display labels + badge tones shared by dashboard / lists / workspace. */

export const TYPE_LABELS: Record<InterviewType, string> = {
  technical: "Technical",
  behavioral: "Behavioral",
  hr: "HR",
  mixed: "Mixed",
  system_design: "System Design",
};

export const TYPE_TONES: Record<InterviewType, BadgeTone> = {
  technical: "brand",
  behavioral: "ai",
  hr: "warning",
  mixed: "neutral",
  system_design: "muted",
};

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const LEVEL_LABELS: Record<ExperienceLevel, string> = {
  junior: "Entry",
  mid: "Mid",
  senior: "Senior",
};

export const STATUS_LABELS: Record<InterviewStatus, string> = {
  created: "Not started",
  in_progress: "In progress",
  completed: "Completed",
};

export const STATUS_TONES: Record<InterviewStatus, BadgeTone> = {
  created: "neutral",
  in_progress: "ai",
  completed: "success",
};
