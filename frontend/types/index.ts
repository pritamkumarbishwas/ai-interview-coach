export type InterviewType =
  | "technical"
  | "behavioral"
  | "hr"
  | "mixed"
  | "system_design";
export type ExperienceLevel = "junior" | "mid" | "senior";
export type Difficulty = "beginner" | "intermediate" | "advanced";
export type InterviewStatus = "created" | "in_progress" | "completed";
export type NextStep = "follow_up" | "harder" | "easier" | "new_topic";

export interface User {
  id: string;
  name: string;
  email: string;
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
  target_questions: number;
  questions: Question[];
  answers: AnswerRecord[];
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
  evaluation: Evaluation;
  created_at: string;
}

/** Response of `POST /api/questions/{id}/answer`. */
export interface AnswerResult {
  question_id: string;
  status: InterviewStatus;
  evaluation: Evaluation;
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
