export type InterviewType = "technical" | "behavioral" | "hr" | "mixed";
export type ExperienceLevel = "entry" | "mid" | "senior" | "lead";
export type Difficulty = "easy" | "medium" | "hard";
export type InterviewStatus = "created" | "in_progress" | "completed";

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

export interface Interview {
  id: string | number;
  role: string;
  interview_type: InterviewType;
  difficulty: Difficulty;
  status: InterviewStatus;
  total_questions: number;
  current_question: number;
  created_at: string;
  completed_at?: string | null;
}

export interface CreateInterviewInput {
  resume_id?: string | number | null;
  job_description_id?: string | number | null;
  role: string;
  experience_level: ExperienceLevel;
  interview_type: InterviewType;
  difficulty: Difficulty;
  total_questions: number;
}

export interface Question {
  id: string | number;
  interview_id: string | number;
  question_text: string;
  category: string;
  difficulty: Difficulty;
  topic: string;
  order_number: number;
}

export interface AnswerSubmission {
  answer_text: string;
}

export interface AnswerEvaluation {
  id?: number;
  overall_score: number;
  relevance_score: number;
  technical_score: number;
  completeness_score: number;
  clarity_score: number;
  strengths: string[];
  weaknesses: string[];
  feedback: string;
  improved_answer: string;
  follow_up?: string | null;
  next_question?: Question | null;
}

export interface AnswerResponse {
  evaluation: AnswerEvaluation;
  next_question?: Question | null;
  interview_completed?: boolean;
}

export interface Report {
  id: string | number;
  interview_id: string | number;
  overall_score: number;
  technical_score?: number;
  communication_score?: number;
  strengths: string[];
  weaknesses: string[];
  strong_topics: string[];
  weak_topics: string[];
  recommended_topics: string[];
  preparation_plan: string[] | string;
  created_at: string;
}
