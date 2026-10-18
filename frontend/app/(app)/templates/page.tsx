"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ChevronRight, ClipboardList, Plus } from "lucide-react";

import { RequireRole } from "@/components/auth/require-role";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea, inputClasses } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import { PROCTORING_LABELS, STAFF_ROLES, defaultTemplateConfig } from "@/lib/recruiting";
import { formatDate } from "@/lib/utils";
import * as templateService from "@/services/templates";
import type { ProctoringMode } from "@/types";

export default function TemplatesPage() {
  return (
    <RequireRole roles={STAFF_ROLES}>
      <Templates />
    </RequireRole>
  );
}

function Templates() {
  const router = useRouter();
  const {
    data: templates,
    loading,
    error,
    reload,
  } = useAsync(() => templateService.listTemplates(), []);
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            Interview templates
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            Standardized rounds, timing, and integrity policy for consistent
            screening.
          </p>
        </div>
        <Button
          className="ml-auto"
          icon={<Plus className="h-4 w-4" aria-hidden />}
          onClick={() => setCreateOpen(true)}
        >
          New template
        </Button>
      </header>

      {error ? (
        <Alert tone="error">
          Couldn&apos;t load templates: {error.message}
          <button
            type="button"
            onClick={reload}
            className="ml-2 font-medium underline"
          >
            Retry
          </button>
        </Alert>
      ) : null}

      {loading && !templates ? (
        <SkeletonList rows={4} />
      ) : templates && templates.length > 0 ? (
        <div className="space-y-3">
          {templates.map((template) => (
            <Link
              key={template.id}
              href={`/templates/${template.id}`}
              className="block"
            >
              <Card className="transition-shadow hover:shadow-[0_4px_12px_rgba(16,24,40,0.06)]">
                <CardContent className="flex items-center gap-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
                    <ClipboardList className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-[15px] font-semibold text-ink">
                        {template.name}
                      </h3>
                      <Badge tone="neutral">
                        {PROCTORING_LABELS[template.proctoring_mode]}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-[13px] text-ink-2">
                      {template.round_count} round
                      {template.round_count === 1 ? "" : "s"} ·{" "}
                      {template.question_count} bank question
                      {template.question_count === 1 ? "" : "s"} ·{" "}
                      {formatDate(template.created_at)}
                    </p>
                  </div>
                  <ChevronRight
                    className="h-5 w-5 shrink-0 text-ink-3"
                    aria-hidden
                  />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ClipboardList className="h-6 w-6" aria-hidden />}
          title="No templates yet"
          description="A template defines the rounds, difficulty, and proctoring policy candidates are screened with."
          action={
            <Button
              icon={<Plus className="h-4 w-4" aria-hidden />}
              onClick={() => setCreateOpen(true)}
            >
              New template
            </Button>
          }
        />
      )}

      <NewTemplateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => router.push(`/templates/${id}`)}
      />
    </div>
  );
}

interface NewTemplateModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}

function NewTemplateModal({ open, onClose, onCreated }: NewTemplateModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [proctoring, setProctoring] = useState<ProctoringMode>("strict");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("A template name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const config = defaultTemplateConfig();
      config.proctoring_mode = proctoring;
      const created = await templateService.createTemplate({
        name: name.trim(),
        description: description.trim(),
        config,
      });
      setName("");
      setDescription("");
      setProctoring("strict");
      onCreated(created.id);
    } catch (caught) {
      setError(toApiError(caught).message);
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New template"
      description="You can fine-tune rounds and questions next."
      className="max-w-lg"
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}

        <Field label="Name" htmlFor="template-name" required>
          <Input
            id="template-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Backend screening — intermediate"
          />
        </Field>

        <Field label="Description" htmlFor="template-description" optional>
          <Textarea
            id="template-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What this template is used for."
          />
        </Field>

        <Field label="Proctoring" htmlFor="template-proctoring">
          <select
            id="template-proctoring"
            className={inputClasses}
            value={proctoring}
            onChange={(event) =>
              setProctoring(event.target.value as ProctoringMode)
            }
          >
            {(Object.keys(PROCTORING_LABELS) as ProctoringMode[]).map((value) => (
              <option key={value} value={value}>
                {PROCTORING_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>

        <div className="flex items-center justify-end gap-3 pt-1">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            Create template
          </Button>
        </div>
      </form>
    </Modal>
  );
}
