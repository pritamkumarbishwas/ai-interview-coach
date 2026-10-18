"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";

import { Briefcase, ChevronRight, Plus } from "lucide-react";

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
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import { JOB_STATUS_LABELS, JOB_STATUS_TONES, STAFF_ROLES } from "@/lib/recruiting";
import { formatDate } from "@/lib/utils";
import * as jobService from "@/services/jobs";
import * as templateService from "@/services/templates";
import type { JobStatus } from "@/types";

export default function JobsPage() {
  return (
    <RequireRole roles={STAFF_ROLES}>
      <Jobs />
    </RequireRole>
  );
}

function Jobs() {
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "recruiter";
  const {
    data: jobs,
    loading,
    error,
    reload,
  } = useAsync(() => jobService.listJobs(), []);
  const { data: templates } = useAsync(
    () => (canManage ? templateService.listTemplates() : Promise.resolve([])),
    [canManage],
  );

  const [createOpen, setCreateOpen] = useState(false);

  const templateName = (templateId: string | null) =>
    templates?.find((template) => template.id === templateId)?.name ?? null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            Job requisitions
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            {canManage
              ? "Openings you're hiring for. Attach an interview template and invite candidates."
              : "Requisitions you've been asked to review."}
          </p>
        </div>
        {canManage ? (
          <Button
            className="ml-auto"
            icon={<Plus className="h-4 w-4" aria-hidden />}
            onClick={() => setCreateOpen(true)}
          >
            New job
          </Button>
        ) : null}
      </header>

      {error ? (
        <Alert tone="error">
          Couldn&apos;t load jobs: {error.message}
          <button
            type="button"
            onClick={reload}
            className="ml-2 font-medium underline"
          >
            Retry
          </button>
        </Alert>
      ) : null}

      {loading && !jobs ? (
        <SkeletonList rows={4} />
      ) : jobs && jobs.length > 0 ? (
        <div className="space-y-3">
          {jobs.map((job) => (
            <Link key={job.id} href={`/jobs/${job.id}`} className="block">
              <Card className="transition-shadow hover:shadow-card-hover">
                <CardContent className="flex items-center gap-4">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
                    <Briefcase className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-[15px] font-semibold text-ink">
                        {job.title}
                      </h3>
                      <Badge tone={JOB_STATUS_TONES[job.status]}>
                        {JOB_STATUS_LABELS[job.status]}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-[13px] text-ink-2">
                      {job.company || "No company set"}
                      {" · "}
                      {templateName(job.template_id) ?? "No template attached"}
                      {" · "}
                      {formatDate(job.created_at)}
                    </p>
                  </div>
                  <ChevronRight className="h-5 w-5 shrink-0 text-ink-3" aria-hidden />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Briefcase className="h-6 w-6" aria-hidden />}
          title={canManage ? "No jobs yet" : "No jobs assigned to you"}
          description={
            canManage
              ? "Create your first requisition to attach an interview template and start inviting candidates."
              : "A recruiter hasn't assigned you to review any requisitions yet."
          }
          action={
            canManage ? (
              <Button
                icon={<Plus className="h-4 w-4" aria-hidden />}
                onClick={() => setCreateOpen(true)}
              >
                New job
              </Button>
            ) : undefined
          }
        />
      )}

      <NewJobModal
        open={canManage && createOpen}
        onClose={() => setCreateOpen(false)}
        templates={templates ?? []}
        onCreated={() => {
          setCreateOpen(false);
          reload();
        }}
      />
    </div>
  );
}

interface NewJobModalProps {
  open: boolean;
  onClose: () => void;
  templates: { id: string; name: string }[];
  onCreated: () => void;
}

function NewJobModal({ open, onClose, templates, onCreated }: NewJobModalProps) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<JobStatus>("draft");
  const [templateId, setTemplateId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle("");
    setCompany("");
    setLocation("");
    setDescription("");
    setStatus("draft");
    setTemplateId("");
    setError(null);
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setError("A job title is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await jobService.createJob({
        title: title.trim(),
        company: company.trim(),
        location: location.trim(),
        description,
        status,
        template_id: templateId || null,
      });
      reset();
      onCreated();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New job"
      description="A requisition candidates will be screened against."
      className="max-w-lg"
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}

        <Field label="Title" htmlFor="job-title" required>
          <Input
            id="job-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Senior Backend Engineer"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Company" htmlFor="job-company" optional>
            <Input
              id="job-company"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              placeholder="Acme Inc."
            />
          </Field>
          <Field label="Location" htmlFor="job-location" optional>
            <Input
              id="job-location"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Remote / London"
            />
          </Field>
        </div>

        <Field label="Description" htmlFor="job-description" optional>
          <Textarea
            id="job-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Responsibilities, requirements, and context for the role."
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Status" htmlFor="job-status">
            <select
              id="job-status"
              className={inputClasses}
              value={status}
              onChange={(event) => setStatus(event.target.value as JobStatus)}
            >
              {(Object.keys(JOB_STATUS_LABELS) as JobStatus[]).map((value) => (
                <option key={value} value={value}>
                  {JOB_STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Interview template" htmlFor="job-template" optional>
            <select
              id="job-template"
              className={inputClasses}
              value={templateId}
              onChange={(event) => setTemplateId(event.target.value)}
            >
              <option value="">No template</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="flex items-center justify-end gap-3 pt-1">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            Create job
          </Button>
        </div>
      </form>
    </Modal>
  );
}
