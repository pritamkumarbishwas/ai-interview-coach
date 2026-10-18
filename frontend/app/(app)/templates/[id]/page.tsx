"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import {
  ArrowLeft,
  Plus,
  Save,
  Sparkles,
  Trash,
  X,
} from "lucide-react";

import { RequireRole } from "@/components/auth/require-role";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, Input, Textarea, inputClasses } from "@/components/ui/input";
import { FullScreenLoader, SkeletonList } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import {
  DIFFICULTIES,
  INTEGRITY_LABELS,
  INTERVIEW_TYPES,
  PROCTORING_LABELS,
  RESPONSE_MODES,
  RESPONSE_MODE_LABELS,
  STAFF_ROLES,
  newRound,
} from "@/lib/recruiting";
import { DIFFICULTY_LABELS, TYPE_LABELS } from "@/lib/interview";
import { cx } from "@/lib/utils";
import * as templateService from "@/services/templates";
import type {
  BankQuestionInput,
  Difficulty,
  IntegrityPolicy,
  InterviewTemplate,
  InterviewType,
  ProctoringMode,
  ResponseMode,
  RoundConfig,
  TemplateConfig,
  TemplatePreview,
} from "@/types";

interface Draft {
  name: string;
  description: string;
  config: TemplateConfig;
  question_bank: BankQuestionInput[];
}

export default function TemplateBuilderPage() {
  return (
    <RequireRole roles={STAFF_ROLES}>
      <TemplateBuilder />
    </RequireRole>
  );
}

function TemplateBuilder() {
  const router = useRouter();
  const params = useParams<{ id: string }>();

  const {
    data: template,
    loading,
    error,
    reload,
  } = useAsync(() => templateService.getTemplate(params.id), [params.id]);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const seededRef = useRef("");

  useEffect(() => {
    if (!template) return;
    const signature = `${template.id}:${template.updated_at}`;
    if (seededRef.current === signature) return;
    seededRef.current = signature;
    setDraft({
      name: template.name,
      description: template.description,
      config: structuredClone(template.config),
      question_bank: template.question_bank.map((question) => ({
        text: question.text,
        topic: question.topic,
        competency: question.competency,
        interview_type: question.interview_type,
        difficulty: question.difficulty,
      })),
    });
  }, [template]);

  if (loading && !template) return <FullScreenLoader label="Loading template" />;

  if (error || !template) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">{error?.message || "Template not found."}</Alert>
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => router.push("/templates")}>
            Back to templates
          </Button>
        </div>
      </div>
    );
  }

  const updateConfig = (patch: Partial<TemplateConfig>) => {
    if (!draft) return;
    setDraft({ ...draft, config: { ...draft.config, ...patch } });
  };

  const updateRound = (index: number, patch: Partial<RoundConfig>) => {
    if (!draft) return;
    const rounds = draft.config.rounds.map((round, i) =>
      i === index ? { ...round, ...patch } : round,
    );
    updateConfig({ rounds });
  };

  const addRound = () => {
    if (!draft) return;
    updateConfig({ rounds: [...draft.config.rounds, newRound(draft.config.rounds.length)] });
  };

  const removeRound = (index: number) => {
    if (!draft || draft.config.rounds.length <= 1) return;
    updateConfig({
      rounds: draft.config.rounds.filter((_, i) => i !== index),
    });
  };

  const updateQuestion = (index: number, patch: Partial<BankQuestionInput>) => {
    if (!draft) return;
    setDraft({
      ...draft,
      question_bank: draft.question_bank.map((question, i) =>
        i === index ? { ...question, ...patch } : question,
      ),
    });
  };

  const addQuestion = () => {
    if (!draft) return;
    setDraft({
      ...draft,
      question_bank: [
        ...draft.question_bank,
        {
          text: "",
          topic: "",
          competency: "",
          interview_type: null,
          difficulty: null,
        },
      ],
    });
  };

  const removeQuestion = (index: number) => {
    if (!draft) return;
    setDraft({
      ...draft,
      question_bank: draft.question_bank.filter((_, i) => i !== index),
    });
  };

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft) return;
    if (!draft.name.trim()) {
      setSaveError("A template name is required.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await templateService.updateTemplate(template.id, {
        name: draft.name.trim(),
        description: draft.description,
        config: draft.config,
        question_bank: draft.question_bank.filter((q) => q.text.trim()),
      });
      setSaved(true);
      reload();
    } catch (caught) {
      setSaveError(toApiError(caught).message);
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await templateService.deleteTemplate(template.id);
      router.push("/templates");
    } catch (caught) {
      setDeleteError(toApiError(caught).message);
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/templates"
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to templates
        </Link>
        <h2 className="mt-2 text-xl font-bold tracking-tight text-ink lg:text-2xl">
          {template.name}
        </h2>
        <p className="mt-1 text-sm text-ink-2">
          Configure rounds, timing, integrity, and the question bank.
        </p>
      </div>

      {draft ? (
        <form onSubmit={onSave} className="space-y-6" noValidate>
          {saveError ? <Alert tone="error">{saveError}</Alert> : null}
          {saved ? <Alert tone="success">Template saved.</Alert> : null}

          <Card>
            <CardHeader title="Basics" />
            <CardContent className="space-y-4">
              <Field label="Name" htmlFor="t-name" required>
                <Input
                  id="t-name"
                  value={draft.name}
                  onChange={(event) =>
                    setDraft({ ...draft, name: event.target.value })
                  }
                />
              </Field>
              <Field label="Description" htmlFor="t-desc" optional>
                <Textarea
                  id="t-desc"
                  value={draft.description}
                  onChange={(event) =>
                    setDraft({ ...draft, description: event.target.value })
                  }
                />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Integrity policy"
              description="Advisory never auto-rejects — a human always decides."
            />
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <Field label="Proctoring" htmlFor="t-proctoring">
                <select
                  id="t-proctoring"
                  className={inputClasses}
                  value={draft.config.proctoring_mode}
                  onChange={(event) =>
                    updateConfig({
                      proctoring_mode: event.target.value as ProctoringMode,
                    })
                  }
                >
                  {(Object.keys(PROCTORING_LABELS) as ProctoringMode[]).map(
                    (value) => (
                      <option key={value} value={value}>
                        {PROCTORING_LABELS[value]}
                      </option>
                    ),
                  )}
                </select>
              </Field>
              <Field label="Policy" htmlFor="t-integrity">
                <select
                  id="t-integrity"
                  className={inputClasses}
                  value={draft.config.integrity_policy}
                  onChange={(event) =>
                    updateConfig({
                      integrity_policy: event.target.value as IntegrityPolicy,
                    })
                  }
                >
                  {(Object.keys(INTEGRITY_LABELS) as IntegrityPolicy[]).map(
                    (value) => (
                      <option key={value} value={value}>
                        {INTEGRITY_LABELS[value]}
                      </option>
                    ),
                  )}
                </select>
              </Field>
              <Field label="Pauses" htmlFor="t-pauses">
                <label
                  htmlFor="t-pauses"
                  className="flex h-[42px] items-center gap-2.5 rounded-btn border border-line bg-card px-3.5 text-sm text-ink"
                >
                  <input
                    id="t-pauses"
                    type="checkbox"
                    className="h-4 w-4 rounded border-line accent-[#f7931e]"
                    checked={draft.config.allow_pauses}
                    onChange={(event) =>
                      updateConfig({ allow_pauses: event.target.checked })
                    }
                  />
                  Allow pauses
                </label>
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Rounds"
              description="Each round is a stage of the standardized interview."
              actions={
                <Button
                  variant="outline"
                  size="sm"
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                  onClick={addRound}
                >
                  Add round
                </Button>
              }
            />
            <CardContent className="space-y-5">
              {draft.config.rounds.map((round, index) => (
                <RoundEditor
                  key={index}
                  index={index}
                  round={round}
                  canRemove={draft.config.rounds.length > 1}
                  onChange={(patch) => updateRound(index, patch)}
                  onRemove={() => removeRound(index)}
                />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Question bank"
              description="Curated questions the AI can draw from (optional)."
              actions={
                <Button
                  variant="outline"
                  size="sm"
                  icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                  onClick={addQuestion}
                >
                  Add question
                </Button>
              }
            />
            <CardContent className="space-y-4">
              {draft.question_bank.length === 0 ? (
                <p className="text-[13px] text-ink-2">
                  No curated questions yet — the AI will generate them from the
                  template config.
                </p>
              ) : (
                draft.question_bank.map((question, index) => (
                  <QuestionEditor
                    key={index}
                    index={index}
                    question={question}
                    onChange={(patch) => updateQuestion(index, patch)}
                    onRemove={() => removeQuestion(index)}
                  />
                ))
              )}
            </CardContent>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              variant="danger-soft"
              icon={<Trash className="h-4 w-4" aria-hidden />}
              onClick={() => {
                setDeleteError(null);
                setDeleteOpen(true);
              }}
            >
              Delete template
            </Button>
            <Button
              type="submit"
              loading={saving}
              icon={<Save className="h-4 w-4" aria-hidden />}
            >
              Save template
            </Button>
          </div>
        </form>
      ) : (
        <SkeletonList rows={3} />
      )}

      <PreviewPanel template={template} />

      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete this template?"
        description="Templates attached to a job cannot be deleted until detached."
      >
        {deleteError ? (
          <div className="mb-4">
            <Alert tone="error">{deleteError}</Alert>
          </div>
        ) : null}
        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deleting}
            onClick={() => void onDelete()}
          >
            Delete template
          </Button>
        </div>
      </Modal>
    </div>
  );
}

interface RoundEditorProps {
  index: number;
  round: RoundConfig;
  canRemove: boolean;
  onChange: (patch: Partial<RoundConfig>) => void;
  onRemove: () => void;
}

function RoundEditor({
  index,
  round,
  canRemove,
  onChange,
  onRemove,
}: RoundEditorProps) {
  const toggleMode = (mode: ResponseMode) => {
    const has = round.response_modes.includes(mode);
    const next = has
      ? round.response_modes.filter((value) => value !== mode)
      : [...round.response_modes, mode];
    onChange({ response_modes: next.length ? next : [mode] });
  };

  return (
    <div className="rounded-btn border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-[13px] font-semibold text-ink">
          Round {index + 1}
        </h4>
        {canRemove ? (
          <button
            type="button"
            onClick={onRemove}
            className="rounded-btn p-1 text-ink-3 transition-colors hover:bg-mist hover:text-danger"
            aria-label={`Remove round ${index + 1}`}
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Key" htmlFor={`round-${index}-key`}>
          <Input
            id={`round-${index}-key`}
            value={round.key}
            onChange={(event) => onChange({ key: event.target.value })}
          />
        </Field>
        <Field label="Label" htmlFor={`round-${index}-label`} optional>
          <Input
            id={`round-${index}-label`}
            value={round.label}
            onChange={(event) => onChange({ label: event.target.value })}
          />
        </Field>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Type" htmlFor={`round-${index}-type`}>
          <select
            id={`round-${index}-type`}
            className={inputClasses}
            value={round.interview_type}
            onChange={(event) =>
              onChange({ interview_type: event.target.value as InterviewType })
            }
          >
            {INTERVIEW_TYPES.map((value) => (
              <option key={value} value={value}>
                {TYPE_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Difficulty" htmlFor={`round-${index}-difficulty`}>
          <select
            id={`round-${index}-difficulty`}
            className={inputClasses}
            value={round.difficulty}
            onChange={(event) =>
              onChange({ difficulty: event.target.value as Difficulty })
            }
          >
            {DIFFICULTIES.map((value) => (
              <option key={value} value={value}>
                {DIFFICULTY_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Minutes" htmlFor={`round-${index}-minutes`}>
          <Input
            id={`round-${index}-minutes`}
            type="number"
            min={1}
            max={180}
            value={round.duration_minutes}
            onChange={(event) =>
              onChange({ duration_minutes: Number(event.target.value) || 1 })
            }
          />
        </Field>
        <Field label="Questions" htmlFor={`round-${index}-questions`}>
          <Input
            id={`round-${index}-questions`}
            type="number"
            min={1}
            max={20}
            value={round.target_questions}
            onChange={(event) =>
              onChange({ target_questions: Number(event.target.value) || 1 })
            }
          />
        </Field>
      </div>

      <div className="mt-3">
        <p className="text-[13px] font-medium text-ink">Response modes</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {RESPONSE_MODES.map((mode) => {
            const active = round.response_modes.includes(mode);
            return (
              <button
                key={mode}
                type="button"
                aria-pressed={active}
                onClick={() => toggleMode(mode)}
                className={cx(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  active
                    ? "border-brand bg-brand-100 text-brand-hover"
                    : "border-line bg-card text-ink-2 hover:bg-mist",
                )}
              >
                {RESPONSE_MODE_LABELS[mode]}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface QuestionEditorProps {
  index: number;
  question: BankQuestionInput;
  onChange: (patch: Partial<BankQuestionInput>) => void;
  onRemove: () => void;
}

function QuestionEditor({
  index,
  question,
  onChange,
  onRemove,
}: QuestionEditorProps) {
  return (
    <div className="rounded-btn border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <Textarea
          aria-label={`Question ${index + 1}`}
          className="min-h-20"
          placeholder="Question text"
          value={question.text}
          onChange={(event) => onChange({ text: event.target.value })}
        />
        <button
          type="button"
          onClick={onRemove}
          className="rounded-btn p-1 text-ink-3 transition-colors hover:bg-mist hover:text-danger"
          aria-label={`Remove question ${index + 1}`}
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Topic" htmlFor={`q-${index}-topic`} optional>
          <Input
            id={`q-${index}-topic`}
            value={question.topic}
            onChange={(event) => onChange({ topic: event.target.value })}
          />
        </Field>
        <Field label="Competency" htmlFor={`q-${index}-competency`} optional>
          <Input
            id={`q-${index}-competency`}
            value={question.competency}
            onChange={(event) => onChange({ competency: event.target.value })}
          />
        </Field>
        <Field label="Type" htmlFor={`q-${index}-type`} optional>
          <select
            id={`q-${index}-type`}
            className={inputClasses}
            value={question.interview_type ?? ""}
            onChange={(event) =>
              onChange({
                interview_type: (event.target.value || null) as InterviewType | null,
              })
            }
          >
            <option value="">Any</option>
            {INTERVIEW_TYPES.map((value) => (
              <option key={value} value={value}>
                {TYPE_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Difficulty" htmlFor={`q-${index}-difficulty`} optional>
          <select
            id={`q-${index}-difficulty`}
            className={inputClasses}
            value={question.difficulty ?? ""}
            onChange={(event) =>
              onChange({
                difficulty: (event.target.value || null) as Difficulty | null,
              })
            }
          >
            <option value="">Any</option>
            {DIFFICULTIES.map((value) => (
              <option key={value} value={value}>
                {DIFFICULTY_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>
      </div>
    </div>
  );
}

function PreviewPanel({ template }: { template: InterviewTemplate }) {
  const [role, setRole] = useState("");
  const [roundKey, setRoundKey] = useState(template.config.rounds[0]?.key ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<TemplatePreview | null>(null);

  const onPreview = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await templateService.previewTemplateQuestion(template.id, {
        role: role.trim(),
        round_key: roundKey || null,
      });
      setPreview(result);
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Preview a question"
        description="Ask the AI to generate one question from this template."
      />
      <CardContent className="space-y-4">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-56 flex-1">
            <Field label="Role" htmlFor="preview-role" optional>
              <Input
                id="preview-role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                placeholder="Senior Backend Engineer"
              />
            </Field>
          </div>
          <div className="w-48">
            <Field label="Round" htmlFor="preview-round">
              <select
                id="preview-round"
                className={inputClasses}
                value={roundKey}
                onChange={(event) => setRoundKey(event.target.value)}
              >
                {template.config.rounds.map((round) => (
                  <option key={round.key} value={round.key}>
                    {round.label || round.key}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Button
            className="mb-0.5"
            loading={submitting}
            icon={<Sparkles className="h-4 w-4" aria-hidden />}
            onClick={() => void onPreview()}
          >
            Generate
          </Button>
        </div>

        {preview ? (
          <div className="rounded-btn border border-line bg-surface p-4">
            <p className="text-sm leading-relaxed text-ink">{preview.question}</p>
            <p className="mt-2 text-xs text-ink-3">
              {TYPE_LABELS[preview.interview_type]} ·{" "}
              {DIFFICULTY_LABELS[preview.difficulty]}
              {preview.topic ? ` · ${preview.topic}` : ""}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
