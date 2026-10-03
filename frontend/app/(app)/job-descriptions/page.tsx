"use client";

import { useState, type FormEvent } from "react";

import { Briefcase, Plus, Trash } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import * as jdService from "@/services/job-descriptions";
import { formatDate } from "@/lib/utils";
import type { JobDescriptionSummary } from "@/types";

const MIN_DESCRIPTION_LENGTH = 40;

export default function JobDescriptionsPage() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [description, setDescription] = useState("");
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const {
    data: items,
    loading,
    error: listError,
    reload,
  } = useAsync(() => jdService.listJobDescriptions(), []);

  const validate = () => {
    const errors: Record<string, string> = {};
    if (!title.trim()) errors.title = "Job title is required";
    if (!company.trim()) errors.company = "Company is required";
    if (description.trim().length < MIN_DESCRIPTION_LENGTH) {
      errors.description = "Paste at least a few sentences (40+ characters)";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSuccess(null);
    setError(null);
    if (!validate() || submitting) return;

    setSubmitting(true);
    try {
      const created = await jdService.createJobDescription({
        title: title.trim(),
        company: company.trim(),
        raw_text: description.trim(),
      });
      setSuccess(`"${created.title}" was saved.`);
      setTitle("");
      setCompany("");
      setDescription("");
      setFieldErrors({});
      reload();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  };

  const removeItem = async (id: string) => {
    setDeletingId(id);
    setError(null);
    try {
      await jdService.deleteJobDescription(id);
      reload();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setDeletingId(null);
    }
  };

  const showListSkeleton = loading && items === null;
  const list = items ?? [];

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-bold tracking-tight text-ink">
          Job Descriptions
        </h2>
        <p className="mt-1.5 text-sm text-ink-2">
          Save the postings you are targeting so questions match the role.
        </p>
      </section>

      <Card>
        <CardHeader
          title="Add a job description"
          description="Paste the posting you are applying for. Required skills are extracted to shape your questions."
        />
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            {error ? <Alert tone="error">{error}</Alert> : null}
            {success ? <Alert tone="success">{success}</Alert> : null}

            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field
                label="Job title"
                htmlFor="jd-title"
                required
                error={fieldErrors.title}
              >
                <Input
                  id="jd-title"
                  placeholder="Senior Backend Engineer"
                  value={title}
                  invalid={Boolean(fieldErrors.title)}
                  aria-invalid={Boolean(fieldErrors.title)}
                  aria-describedby={
                    fieldErrors.title ? "jd-title-error" : undefined
                  }
                  onChange={(event) => setTitle(event.target.value)}
                />
              </Field>
              <Field
                label="Company"
                htmlFor="jd-company"
                required
                error={fieldErrors.company}
              >
                <Input
                  id="jd-company"
                  placeholder="Acme Inc."
                  value={company}
                  invalid={Boolean(fieldErrors.company)}
                  aria-invalid={Boolean(fieldErrors.company)}
                  aria-describedby={
                    fieldErrors.company ? "jd-company-error" : undefined
                  }
                  onChange={(event) => setCompany(event.target.value)}
                />
              </Field>
            </div>

            <Field
              label="Job description"
              htmlFor="jd-description"
              required
              error={fieldErrors.description}
              hint={`${description.trim().length} characters`}
            >
              <Textarea
                id="jd-description"
                rows={8}
                placeholder="Paste the responsibilities, requirements, and nice-to-haves…"
                value={description}
                invalid={Boolean(fieldErrors.description)}
                aria-invalid={Boolean(fieldErrors.description)}
                aria-describedby={
                  fieldErrors.description ? "jd-description-error" : undefined
                }
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>

            <div className="flex justify-end">
              <Button
                type="submit"
                loading={submitting}
                icon={<Plus className="h-4 w-4" aria-hidden />}
              >
                {submitting ? "Extracting skills…" : "Save job description"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <section aria-label="Saved job descriptions" className="space-y-3">
        <h2 className="text-sm font-semibold text-ink">
          Saved job descriptions{" "}
          <span className="font-normal text-ink-3">({list.length})</span>
        </h2>

        {listError ? (
          <Alert tone="error">
            {listError.message}{" "}
            <button
              type="button"
              onClick={reload}
              className="font-medium underline"
            >
              Retry
            </button>
          </Alert>
        ) : showListSkeleton ? (
          <SkeletonList rows={3} />
        ) : list.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {list.map((item) => (
              <JobDescriptionCard
                key={item.id}
                item={item}
                busy={deletingId === item.id}
                onRemove={() => void removeItem(item.id)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Briefcase className="h-5 w-5" />}
            title="No job descriptions yet"
            description="Add the role you are targeting so every question matches the job."
          />
        )}
      </section>
    </div>
  );
}

function JobDescriptionCard({
  item,
  busy,
  onRemove,
}: {
  item: JobDescriptionSummary;
  busy: boolean;
  onRemove: () => void;
}) {
  return (
    <Card>
      <CardContent>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">
              {item.title}
            </p>
            <p className="mt-0.5 truncate text-sm text-ink-2">{item.company}</p>
          </div>
          <div className="flex items-center gap-1">
            <Badge tone="ai">JD</Badge>
            <button
              type="button"
              onClick={onRemove}
              disabled={busy}
              aria-label={`Delete ${item.title}`}
              className="rounded-btn p-1.5 text-ink-3 transition-colors hover:bg-[#fdf0f0] hover:text-danger disabled:opacity-50"
            >
              <Trash className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-ink-2">
          {item.snippet}
        </p>
        <p className="mt-3 text-xs text-ink-3">
          Added {formatDate(item.created_at)}
        </p>
      </CardContent>
    </Card>
  );
}
