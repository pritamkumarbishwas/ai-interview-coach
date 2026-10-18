export type InterviewType =
  | "technical"
  | "behavioral"
  | "hr"
  | "mixed"
  | "system_design";
export type ExperienceLevel = "junior" | "mid" | "senior";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type InterviewStatus = "created" | "in_progress" | "completed";
export type ProctoringMode = "off" | "camera_only" | "strict";
export type NextStep = "follow_up" | "harder" | "easier" | "new_topic";
export type Role = "candidate" | "admin" | "recruiter" | "reviewer";

export const STAFF_ROLES: Role[] = ["admin", "recruiter", "reviewer"];

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  created_at: string;
}



export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface Resume {
  id: string;
  filename: string;
  file_size?: number;
  raw_text?: string;
  structured_data?: Record<string, unknown> | null;
  created_at: string;
}

export interface ResumeSummary {
  id: string;
  filename: string;
  file_size: number;
  skills: string[];
  created_at: string;
}

export interface ResumeUploadResponse {
  id: string;
  filename: string;
  structured_data: Record<string, unknown>;
}

export interface JobDescription {
  id: string;
  title: string;
  company: string;
  raw_text: string;
  snippet?: string;
  structured_data?: Record<string, unknown> | null;
  created_at: string;
}

export interface JobDescriptionSummary {
  id: string;
  title: string;
  company: string;
  snippet: string;
  created_at: string;
}

export interface CreateJobDescriptionInput {
  title: string;
  company: string;
  raw_text: string;
}

/** Row returned by `GET /api/interviews` (list). */
export interface InterviewSummary {
  id: string;
  role: string;
  type: InterviewType;
  difficulty: Difficulty;
  status: InterviewStatus;
  question_count: number;
  answered_count: number;
  target_questions: number;
  created_at: string;
}

export interface CreateInterviewInput {
  resume_id?: string;
  jd_id?: string;
  role: string;
  level: ExperienceLevel;
  type: InterviewType;
  difficulty: Difficulty;
  target_questions: number;
}

export interface Question {
  id: string;
  sequence: number;
  text: string;
  topic: string;
}

export interface ProctoringSession {
  consent_given_at: string | null;
}

/** Metadata for the session recording (kind = "camera" composite). */
export interface RecordingMeta {
  file_id: string;
  content_type: string;
  size_bytes: number;
  chunk_count: number;
  finalized: boolean;
  created_at: string;
  updated_at: string;
}

/** Full document returned by `GET /api/interviews/{id}` (detail). */
export interface InterviewDetail {
  id: string;
  resume_id: string;
  jd_id: string;
  role: string;
  level: ExperienceLevel;
  type: InterviewType;
  difficulty: Difficulty;
  status: InterviewStatus;
  proctoring_mode: ProctoringMode;
  proctoring_session: ProctoringSession | null;
  target_questions: number;
  questions: Question[];
  answers: AnswerRecord[];
  recordings: Partial<Record<string, RecordingMeta>>;
  current_question_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ScoreBreakdown {
  technical: number;
  relevance: number;
  completeness: number;
  structure: number;
  clarity: number;
}

export interface Evaluation {
  scores: ScoreBreakdown;
  overall: number;
  strengths: string[];
  weaknesses: string[];
  feedback: string;
  improved_answer: string;
  next_step: NextStep;
  created_at: string;
}

export interface AnswerRecord {
  id: string;
  question_id: string;
  text: string;
  /** Deferred: `null` until the end-of-exam evaluation has run. */
  evaluation: Evaluation | null;
  created_at: string;
}

/** Response of `POST /api/questions/{id}/answer`. */
export interface AnswerResult {
  question_id: string;
  status: InterviewStatus;
  /** Always `null` during the session — scoring is deferred to exam end. */
  evaluation: Evaluation | null;
  next_question: Question | null;
  questions_answered: number;
  target_questions: number;
}

/** Response of `POST /interviews/{id}/start` and `GET .../current-question`. */
export interface CurrentQuestion {
  interview_id: string;
  status: InterviewStatus;
  question: Question;
  question_number: number;
  total_asked: number;
}

export interface PreparationStep {
  focus: string;
  actions: string[];
}

/** Response of `GET /api/interviews/{id}/report`. */
export interface Report {
  interview_id: string;
  overall_score: number;
  technical_score: number;
  communication_score: number;
  strong_topics: string[];
  weak_topics: string[];
  topics_to_study: string[];
  narrative: string;
  preparation_plan: PreparationStep[];
  generated_at: string;
}

export interface DashboardInterview {
  id: string;
  role: string;
  type: InterviewType;
  difficulty: Difficulty;
  status: InterviewStatus;
  target_questions: number;
  answered_count: number;
  score: number | null;
  created_at: string;
}

/** Response of `GET /api/dashboard/stats`. */
export interface DashboardStats {
  interviews_total: number;
  interviews_completed: number;
  interviews_in_progress: number;
  questions_answered: number;
  average_score: number | null;
  strong_topics: string[];
  weak_topics: string[];
  recent: DashboardInterview[];
}

/* ---- Recruiter: job requisitions ---------------------------------------- */

export type JobStatus = "draft" | "open" | "closed";

export interface JobSummary {
  id: string;
  title: string;
  company: string;
  status: JobStatus;
  template_id: string | null;
  created_at: string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  status: JobStatus;
  template_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateJobInput {
  title: string;
  company?: string;
  location?: string;
  description?: string;
  status?: JobStatus;
  template_id?: string | null;
}

export type UpdateJobInput = Partial<CreateJobInput>;

/* ---- Recruiter: interview templates ------------------------------------- */

export type ResponseMode = "voice" | "typed" | "code" | "whiteboard";
export type IntegrityPolicy = "advisory" | "strict";

export interface RoundConfig {
  key: string;
  label: string;
  interview_type: InterviewType;
  difficulty: Difficulty;
  duration_minutes: number;
  target_questions: number;
  response_modes: ResponseMode[];
}

export interface TemplateConfig {
  proctoring_mode: ProctoringMode;
  integrity_policy: IntegrityPolicy;
  allow_pauses: boolean;
  rounds: RoundConfig[];
}

export interface BankQuestion {
  id: string;
  text: string;
  topic: string;
  competency: string;
  interview_type: InterviewType | null;
  difficulty: Difficulty | null;
}

export type BankQuestionInput = Omit<BankQuestion, "id">;

export interface TemplateSummary {
  id: string;
  name: string;
  description: string;
  proctoring_mode: ProctoringMode;
  round_count: number;
  question_count: number;
  created_at: string;
}

export interface InterviewTemplate {
  id: string;
  name: string;
  description: string;
  config: TemplateConfig;
  question_bank: BankQuestion[];
  created_at: string;
  updated_at: string;
}

export interface CreateTemplateInput {
  name: string;
  description?: string;
  config?: TemplateConfig;
  question_bank?: BankQuestionInput[];
}

export type UpdateTemplateInput = Partial<CreateTemplateInput>;

export interface TemplatePreviewInput {
  role?: string;
  round_key?: string | null;
  interview_type?: InterviewType;
  difficulty?: Difficulty;
  topic?: string;
}

export interface TemplatePreview {
  question: string;
  topic: string;
  interview_type: InterviewType;
  difficulty: Difficulty;
}

/* ---- Candidate invitations ---------------------------------------------- */

export type InvitationStatus =
  | "pending"
  | "started"
  | "completed"
  | "expired"
  | "revoked";

/** Human review decision; the AI never sets this. */
export type Decision = "pending" | "advance" | "hold" | "decline";

export interface Invitation {
  id: string;
  job_id: string;
  candidate_name: string;
  candidate_email: string;
  role: string;
  status: InvitationStatus;
  expires_at: string;
  round_minutes: number;
  round_deadline: string | null;
  interview_id: string | null;
  decision: Decision;
  decision_note: string;
  decided_at: string | null;
  created_at: string;
  accept_url: string | null;
}

export interface ShortlistEntry {
  invitation_id: string;
  candidate_name: string;
  candidate_email: string;
  status: InvitationStatus;
  decision: Decision;
  overall_score: number;
  threshold: number;
  meets_threshold: boolean;
  competency_count: number;
  /** Cohort-relative context (advisory; null until at least one peer is scored). */
  percentile: number | null;
  z_score: number | null;
  integrity_level: IntegrityLevel | null;
  integrity_score: number | null;
  generated_at: string | null;
}

export interface CreateInvitationInput {
  job_id: string;
  candidate_email: string;
  candidate_name?: string;
  round_key?: string | null;
  start_window_start?: string | null;
  start_window_end?: string | null;
  expires_in_days?: number;
  /** Extra round time for an accessibility accommodation (minutes). */
  extra_minutes?: number;
}

/** Pre-check payload for a magic-link candidate (no account, no scores). */
export interface InvitationSession {
  status: InvitationStatus;
  role: string;
  company: string;
  interview_type: InterviewType;
  difficulty: Difficulty;
  proctoring_mode: ProctoringMode;
  consent_required: boolean;
  total_questions: number;
  started: boolean;
  expires_at: string;
  start_window_start: string | null;
  start_window_end: string | null;
  round_deadline: string | null;
}

/** Advisory integrity summary for a candidate session (never a verdict). */
export type IntegrityLevel = "low" | "moderate" | "elevated" | "high";

export interface IntegritySignalCount {
  type: string;
  label: string;
  count: number;
  weight: number;
}

export interface IntegrityMoment {
  at: string | null;
  type: string;
  label: string;
  severity: number;
  details: Record<string, unknown>;
}

export interface IntegrityReport {
  interview_id: string;
  advisory: boolean;
  score: number;
  level: IntegrityLevel;
  session_started_at: string | null;
  session_ended_at: string | null;
  recording_available: boolean;
  recording_size_bytes: number;
  signals: IntegritySignalCount[];
  moments: IntegrityMoment[];
  notes: string[];
  generated_at: string;
}

/* ---- Scorecard (advisory competency scoring) ---------------------------- */

export interface CompetencyEvidence {
  question_id: string;
  topic: string;
  score: number;
  quotes: string[];
}

export interface CompetencyScore {
  competency: string;
  score: number;
  answered: number;
  evidence: CompetencyEvidence[];
}

export interface Scorecard {
  interview_id: string;
  role: string;
  advisory: boolean;
  overall_score: number;
  competencies: CompetencyScore[];
  strengths: string[];
  concerns: string[];
  recommendation: string;
  threshold: number;
  meets_threshold: boolean;
  identity_hidden: boolean;
  generated_at: string;
}

/* ---- Review timeline (transcript ↔ recording navigation) ---------------- */

export type TimelineEntryKind = "answer" | "signal";

export interface TimelineEntry {
  kind: TimelineEntryKind;
  /** Seconds from the start of the recording (media time 0). */
  at_seconds: number;
  at: string | null;
  label: string;
  question_id: string;
  question: string;
  answer: string;
  competency: string;
  score: number | null;
  severity: number;
}

export interface ReviewTimeline {
  interview_id: string;
  /** True when offsets are anchored to the client-reported recorder start. */
  anchored_to_recording: boolean;
  recording_available: boolean;
  duration_seconds: number;
  entries: TimelineEntry[];
  generated_at: string;
}

/* ---- Staff & roles ------------------------------------------------------ */

export type StaffInvitationStatus = "pending" | "accepted" | "revoked";

export interface StaffInvitation {
  id: string;
  email: string;
  role: Role;
  status: StaffInvitationStatus;
  expires_at: string;
  created_at: string;
  accept_url: string | null;
}

export interface CreateStaffInvitationInput {
  email: string;
  role: Role;
  name?: string;
}

export interface AcceptStaffInvitationInput {
  token: string;
  name: string;
  password: string;
}

/* ---- Audit -------------------------------------------------------------- */

export interface AuditLog {
  id: string;
  actor_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
