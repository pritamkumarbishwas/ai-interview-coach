"use client";

import { useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  FileUp,
  Mic,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/input";
import { toApiError } from "@/lib/api";
import { cx } from "@/lib/utils";
import { createJobDescription } from "@/services/job-descriptions";
import { uploadResume } from "@/services/resumes";
import {
  createInterview,
  startInterview,
} from "@/services/interviews";
import type {
  Difficulty,
  ExperienceLevel,
  InterviewType,
} from "@/types";

const INTERVIEW_TYPES: { value: InterviewType; label: string }[] = [
  { value: "technical", label: "Technical" },
  { value: "behavioral", label: "Behavioral" },
  { value: "hr", label: "HR" },
  { value: "mixed", label: "Mixed" },
  { value: "system_design", label: "System Design" },
];

const DIFFICULTIES: { value: Difficulty; label: string }[] = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "junior", label: "Entry" },
  { value: "mid", label: "Mid" },
  { value: "senior", label: "Senior" },
];

const ACCEPTED_EXTENSIONS = [".pdf", ".docx"];
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

function clampQuestionCount(value: number): number {
  if (!Number.isFinite(value)) return 10;
  return Math.min(15, Math.max(5, Math.round(value)));
}

export default function PracticePage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [jobDescription, setJobDescription] = useState("");
  const [role, setRole] = useState("Full Stack Developer");
  const [experience, setExperience] = useState<ExperienceLevel>("mid");
  const [type, setType] = useState<InterviewType>("technical");
  const [difficulty, setDifficulty] = useState<Difficulty>("intermediate");
  const [questionCount, setQuestionCount] = useState(10);
  const [fileError, setFileError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const acceptFile = (next?: File) => {
    if (!next) return;
    const lower = next.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setFile(null);
      setFileError("Only PDF and DOCX files are supported.");
      return;
    }
    if (next.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setFileError("That file is larger than 5 MB.");
      return;
    }
    setFileError(null);
    setFile(next);
  };

  const removeFile = () => {
    setFile(null);
    setFileError(null);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  };

  const canContinue = step === 1 || (step === 2 && jobDescription.trim().length > 0);
  const canStart = role.trim().length > 0;

  const handleStart = async () => {
    if (starting) return;
    const target = clampQuestionCount(questionCount);
    setQuestionCount(target);
    setStarting(true);
    setStartError(null);
    try {
      let resumeId: string | undefined;
      if (file) {
        const uploaded = await uploadResume(file);
        resumeId = uploaded.id;
      }
      const jd = await createJobDescription({
        title: role.trim(),
        company: "Not specified",
        raw_text: jobDescription.trim(),
      });
      const interview = await createInterview({
        resume_id: resumeId,
        jd_id: jd.id,
        role: role.trim(),
        level: experience,
        type,
        difficulty,
        target_questions: target,
      });
      // Best effort: pre-generate question 1. On failure the workspace page
      // offers a Start button, so the session is never lost.
      try {
        await startInterview(interview.id);
      } catch {
        // handled by the workspace
      }
      router.push(`/interviews/${interview.id}`);
    } catch (error) {
      setStartError(toApiError(error).message);
      setStarting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section>
        <h2 className="text-2xl font-bold tracking-tight text-ink">
          Start a mock interview
        </h2>
        <p className="mt-1.5 text-sm text-ink-2">
          Three quick steps — upload context, describe the role, configure the
          session.
        </p>
      </section>

      <ol className="flex items-center gap-2" aria-label="Setup progress">
        {["Upload Resume", "Job Description", "Configure"].map((label, index) => {
          const number = index + 1;
          const active = step === number;
          const done = step > number;
          return (
            <li key={label} className="flex flex-1 items-center gap-2">
              <span
                className={cx(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors",
                  done
                    ? "bg-success text-white"
                    : active
                      ? "bg-brand text-white"
                      : "border border-line bg-card text-ink-3",
                )}
                aria-current={active ? "step" : undefined}
              >
                {done ? <Check className="h-3.5 w-3.5" aria-hidden /> : number}
              </span>
              <span
                className={cx(
                  "hidden text-[13px] font-medium sm:block",
                  active ? "text-ink" : "text-ink-3",
                )}
              >
                {label}
              </span>
              {index < 2 ? (
                <span
                  className={cx(
                    "h-px flex-1",
                    step > number ? "bg-success" : "bg-line",
                  )}
                  aria-hidden
                />
              ) : null}
            </li>
          );
        })}
      </ol>

      {step === 1 ? (
        <Card>
          <CardHeader
            title="Upload your resume"
            description="We use it to tailor questions to your experience. PDF or DOCX, up to 5 MB."
          />
          <CardContent>
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cx(
                "flex flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-12 text-center transition-colors",
                dragging
                  ? "border-brand bg-brand-50"
                  : "border-line bg-surface hover:border-[#f3d3a8]",
              )}
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand">
                <FileUp className="h-6 w-6" aria-hidden />
              </span>
              {file ? (
                <>
                  <p className="mt-4 flex items-center gap-2 text-sm font-semibold text-ink">
                    <FileText className="h-4 w-4 text-success" aria-hidden />
                    {file.name}
                  </p>
                  <button
                    type="button"
                    onClick={removeFile}
                    className="mt-1.5 text-[13px] font-medium text-danger hover:underline"
                  >
                    Remove
                  </button>
                </>
              ) : (
                <>
                  <p className="mt-4 text-sm font-medium text-ink">
                    Drag and drop your resume here
                  </p>
                  <p className="mt-1 text-[13px] text-ink-2">or</p>
                  <label className="mt-3 cursor-pointer rounded-btn border border-line bg-card px-4 py-2 text-sm font-medium text-ink-2 shadow-sm transition-colors hover:bg-mist">
                    Browse files
                    <input
                      type="file"
                      accept=".pdf,.docx"
                      className="sr-only"
                      onChange={(event) => {
                        acceptFile(event.target.files?.[0]);
                        event.target.value = "";
                      }}
                    />
                  </label>
                </>
              )}
            </div>
            {fileError ? (
              <Alert tone="error" className="mt-3">
                {fileError}
              </Alert>
            ) : null}
            <p className="mt-3 text-center text-xs text-ink-3">
              Optional — you can skip this and still start an interview.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card>
          <CardHeader
            title="Job description"
            description="Paste the posting you are preparing for so questions match the role."
          />
          <CardContent>
            <Field
              label="Job description"
              htmlFor="jd"
              hint={`${jobDescription.length} characters`}
            >
              <Textarea
                id="jd"
                rows={9}
                value={jobDescription}
                onChange={(event) => setJobDescription(event.target.value)}
                placeholder="Paste the job description here…"
              />
            </Field>
          </CardContent>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card>
          <CardHeader
            title="Configure your session"
            description="Pick the settings that match the interview you want to practice."
          />
          <CardContent className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Target role" htmlFor="role">
                <Input
                  id="role"
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                />
              </Field>
              <Field label="Experience level" htmlFor="experience">
                <select
                  id="experience"
                  value={experience}
                  onChange={(event) =>
                    setExperience(event.target.value as ExperienceLevel)
                  }
                  className="block w-full rounded-btn border border-line bg-card px-3.5 py-2.5 text-sm text-ink shadow-sm transition-colors focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-100"
                >
                  {EXPERIENCE_LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {level.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <fieldset>
              <legend className="mb-2 text-[13px] font-medium text-ink">
                Interview type
              </legend>
              <div className="flex flex-wrap gap-2">
                {INTERVIEW_TYPES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setType(item.value)}
                    aria-pressed={type === item.value}
                    className={cx(
                      "rounded-full border px-3.5 py-1.5 text-[13px] font-medium transition-colors",
                      type === item.value
                        ? "border-brand bg-brand-100 text-brand-hover"
                        : "border-line bg-card text-ink-2 hover:bg-mist",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-2 text-[13px] font-medium text-ink">
                Difficulty
              </legend>
              <div className="grid grid-cols-3 gap-3">
                {DIFFICULTIES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setDifficulty(item.value)}
                    aria-pressed={difficulty === item.value}
                    className={cx(
                      "rounded-xl border px-3 py-3 text-left transition-colors",
                      difficulty === item.value
                        ? "border-brand bg-brand-50"
                        : "border-line bg-card hover:bg-mist",
                    )}
                  >
                    <span className="block text-sm font-semibold text-ink">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-2">
                      {item.value === "beginner"
                        ? "Warm-up basics"
                        : item.value === "intermediate"
                          ? "Realistic screen"
                          : "Hard, senior-level"}
                    </span>
                  </button>
                ))}
              </div>
            </fieldset>

            <Field label="Number of questions" htmlFor="count" hint="5 – 15">
              <Input
                id="count"
                type="number"
                min={5}
                max={15}
                value={questionCount}
                onChange={(event) => setQuestionCount(Number(event.target.value))}
                onBlur={() => setQuestionCount(clampQuestionCount(questionCount))}
              />
            </Field>
          </CardContent>
        </Card>
      ) : null}

      {startError ? (
        <Alert tone="error">{startError}</Alert>
      ) : null}

      <div className="flex items-center justify-between gap-3">
        <Button
          variant="ghost"
          onClick={() => setStep((value) => Math.max(1, value - 1))}
          disabled={step === 1 || starting}
          icon={<ArrowLeft className="h-4 w-4" />}
        >
          Back
        </Button>

        {step < 3 ? (
          <Button
            onClick={() => setStep((value) => Math.min(3, value + 1))}
            disabled={!canContinue}
            icon={<ArrowRight className="h-4 w-4" />}
          >
            Continue
          </Button>
        ) : (
          <Button
            onClick={handleStart}
            disabled={!canStart || starting}
            loading={starting}
            icon={<Mic className="h-4 w-4" />}
          >
            {starting ? "Creating…" : "Start AI Interview"}
          </Button>
        )}
      </div>
    </div>
  );
}
