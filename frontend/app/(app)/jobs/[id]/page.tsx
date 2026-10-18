"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import {
  ArrowLeft,
  BellRing,
  Check,
  Clock,
  Copy,
  Download,
  Film,
  Gauge,
  Save,
  ShieldCheck,
  Trash,
  UserPlus,
} from "lucide-react";

import { RequireRole } from "@/components/auth/require-role";
import {
  CandidateTimelineModal,
  CompareCandidatesButton,
} from "@/components/recruiting/candidate-review";
import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, Textarea, inputClasses } from "@/components/ui/input";
import { FullScreenLoader, SkeletonList } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { useAsync } from "@/hooks/use-async";
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import {
  INTEGRITY_LEVEL_LABELS,
  INTEGRITY_LEVEL_TONES,
  JOB_STATUS_LABELS,
  JOB_STATUS_TONES,
  STAFF_ROLES,
} from "@/lib/recruiting";
import { cx, formatDate, formatTime } from "@/lib/utils";import * as invitationService from "@/services/invitations";
import * as jobService from "@/services/jobs";
import * as staffService from "@/services/staff";
import * as templateService from "@/services/templates";
import type {
  BiasVerdict,
  Decision,
  IntegrityReport,
  Invitation,
  InvitationStatus,
  Job,
  JobStatus,
  Scorecard,
  ShadowReport,
  ShortlistEntry,
} from "@/types";

const INVITATION_TONES: Record<InvitationStatus, BadgeTone> = {
  pending: "warning",
  started: "ai",
  completed: "success",
  expired: "muted",
  revoked: "danger",
};

const INVITATION_LABELS: Record<InvitationStatus, string> = {
  pending: "Pending",
  started: "In progress",
  completed: "Completed",
  expired: "Expired",
  revoked: "Revoked",
};

function CopyLinkButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be blocked; the link stays selectable in the input.
    }
  };
  return (
    <Button
      variant="outline"
      size="sm"
      icon={
        copied ? (
          <Check className="h-3.5 w-3.5" aria-hidden />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden />
        )
      }
      onClick={() => void onCopy()}
    >
      {copied ? "Copied" : "Copy link"}
    </Button>
  );
}

function ReviewersPanel({ job, onSaved }: { job: Job; onSaved: () => void }) {
  const {
    data: reviewers,
    loading,
    error,
  } = useAsync(() => staffService.listReviewers(), []);
  const [selected, setSelected] = useState<string[]>(job.reviewer_ids ?? []);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSelected(job.reviewer_ids ?? []);
  }, [job.id, job.reviewer_ids]);

  const toggle = (id: string) => {
    setSaved(false);
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await jobService.setJobReviewers(job.id, selected);
      setSaved(true);
      onSaved();
    } catch (caught) {
      setSaveError(toApiError(caught).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {saveError ? <Alert tone="error">{saveError}</Alert> : null}
      {saved ? <Alert tone="success">Reviewers updated.</Alert> : null}

      {loading && !reviewers ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <Alert tone="error">{error.message}</Alert>
      ) : !reviewers || reviewers.length === 0 ? (
        <p className="text-[13px] text-ink-2">
          No reviewer accounts yet. An admin can invite reviewers from the Team
          page.
        </p>
      ) : (
        <>
          <ul className="space-y-2">
            {reviewers.map((reviewer) => (
              <li
                key={reviewer.id}
                className="flex items-center gap-3 rounded-btn border border-line px-3.5 py-2.5"
              >
                <input
                  type="checkbox"
                  id={`reviewer-${reviewer.id}`}
                  checked={selected.includes(reviewer.id)}
                  onChange={() => toggle(reviewer.id)}
                  className="h-4 w-4 shrink-0 rounded border-line text-brand focus:ring-brand"
                />
                <label
                  htmlFor={`reviewer-${reviewer.id}`}
                  className="min-w-0 flex-1 cursor-pointer"
                >
                  <span className="block truncate text-[13px] font-medium text-ink">
                    {reviewer.name}
                  </span>
                  <span className="block truncate text-xs text-ink-2">
                    {reviewer.email}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="flex justify-end">
            <Button
              loading={saving}
              icon={<Save className="h-4 w-4" aria-hidden />}
              onClick={() => void save()}
            >
              Save reviewers
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function ReadOnlyJobDetails({ job }: { job: Job }) {
  const rows: { label: string; value: string; pre?: boolean }[] = [
    { label: "Title", value: job.title },
    { label: "Company", value: job.company || "—" },
    { label: "Location", value: job.location || "—" },
    { label: "Status", value: JOB_STATUS_LABELS[job.status] },
    { label: "Description", value: job.description || "—", pre: true },
  ];
  return (
    <dl className="space-y-3">
      {rows.map((row) => (
        <div key={row.label}>
          <dt className="text-xs font-medium text-ink-2">{row.label}</dt>
          <dd
            className={cx(
              "mt-0.5 text-[13px] text-ink",
              row.pre && "whitespace-pre-wrap",
            )}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function JobDetailPage() {
  return (
    <RequireRole roles={STAFF_ROLES}>
      <JobDetail />
    </RequireRole>
  );
}

function JobDetail() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const canManage = user?.role === "admin" || user?.role === "recruiter";

  const {
    data: job,
    loading,
    error,
    reload,
  } = useAsync(() => jobService.getJob(params.id), [params.id]);
  const { data: templates } = useAsync(
    () => (canManage ? templateService.listTemplates() : Promise.resolve([])),
    [canManage],
  );
  const {
    data: invitations,
    loading: invitationsLoading,
    reload: reloadInvitations,
  } = useAsync(() => invitationService.listInvitations(params.id), [params.id]);

  const [form, setForm] = useState<{
    title: string;
    company: string;
    location: string;
    description: string;
    status: JobStatus;
    template_id: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [reviewSignal, setReviewSignal] = useState(0);

  const refreshCandidates = () => {
    reloadInvitations();
    setReviewSignal((signal) => signal + 1);
  };

  const seededRef = useRef("");

  useEffect(() => {
    if (!job) return;
    const signature = `${job.id}:${job.updated_at}`;
    if (seededRef.current === signature) return;
    seededRef.current = signature;
    setForm({
      title: job.title,
      company: job.company,
      location: job.location,
      description: job.description,
      status: job.status,
      template_id: job.template_id ?? "",
    });
  }, [job]);

  if (loading && !job) return <FullScreenLoader label="Loading job" />;

  if (error || !job) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">{error?.message || "Job not found."}</Alert>
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => router.push("/jobs")}>
            Back to jobs
          </Button>
        </div>
      </div>
    );
  }

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    if (!form.title.trim()) {
      setSaveError("A job title is required.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await jobService.updateJob(job.id, {
        title: form.title.trim(),
        company: form.company.trim(),
        location: form.location.trim(),
        description: form.description,
        status: form.status,
        template_id: form.template_id || null,
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
    try {
      await jobService.deleteJob(job.id);
      router.push("/jobs");
    } catch (caught) {
      setSaveError(toApiError(caught).message);
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/jobs"
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2 transition-colors hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          Back to jobs
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2.5">
          <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            {job.title}
          </h2>
          <Badge tone={JOB_STATUS_TONES[job.status]}>
            {JOB_STATUS_LABELS[job.status]}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-ink-2">
          {job.company || "No company set"} · created {formatDate(job.created_at)}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Job details"
            description={canManage ? "Edit the requisition." : "Requisition details."}
          />
          <CardContent>
            {!canManage ? (
              <ReadOnlyJobDetails job={job} />
            ) : form ? (
              <form onSubmit={onSave} className="space-y-4" noValidate>
                {saveError ? <Alert tone="error">{saveError}</Alert> : null}
                {saved ? <Alert tone="success">Job saved.</Alert> : null}

                <Field label="Title" htmlFor="edit-title" required>
                  <Input
                    id="edit-title"
                    value={form.title}
                    onChange={(event) =>
                      setForm({ ...form, title: event.target.value })
                    }
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Company" htmlFor="edit-company" optional>
                    <Input
                      id="edit-company"
                      value={form.company}
                      onChange={(event) =>
                        setForm({ ...form, company: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="Location" htmlFor="edit-location" optional>
                    <Input
                      id="edit-location"
                      value={form.location}
                      onChange={(event) =>
                        setForm({ ...form, location: event.target.value })
                      }
                    />
                  </Field>
                </div>

                <Field label="Description" htmlFor="edit-description" optional>
                  <Textarea
                    id="edit-description"
                    value={form.description}
                    onChange={(event) =>
                      setForm({ ...form, description: event.target.value })
                    }
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Status" htmlFor="edit-status">
                    <select
                      id="edit-status"
                      className={inputClasses}
                      value={form.status}
                      onChange={(event) =>
                        setForm({
                          ...form,
                          status: event.target.value as JobStatus,
                        })
                      }
                    >
                      {(Object.keys(JOB_STATUS_LABELS) as JobStatus[]).map(
                        (value) => (
                          <option key={value} value={value}>
                            {JOB_STATUS_LABELS[value]}
                          </option>
                        ),
                      )}
                    </select>
                  </Field>
                  <Field
                    label="Interview template"
                    htmlFor="edit-template"
                    optional
                  >
                    <select
                      id="edit-template"
                      className={inputClasses}
                      value={form.template_id}
                      onChange={(event) =>
                        setForm({ ...form, template_id: event.target.value })
                      }
                    >
                      <option value="">No template</option>
                      {(templates ?? []).map((template) => (
                        <option key={template.id} value={template.id}>
                          {template.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>

                <div className="flex items-center justify-between gap-3 pt-1">
                  <Button
                    variant="danger-soft"
                    size="sm"
                    icon={<Trash className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => setDeleteOpen(true)}
                  >
                    Delete
                  </Button>
                  <Button
                    type="submit"
                    loading={saving}
                    icon={<Save className="h-4 w-4" aria-hidden />}
                  >
                    Save changes
                  </Button>
                </div>
              </form>
            ) : (
              <SkeletonList rows={3} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Candidates"
            description={
              canManage
                ? "Invite candidates by magic link."
                : "Candidates invited to this role."
            }
          />
          <CardContent className="space-y-5">
            {link ? (
              <div className="rounded-btn border border-info-border bg-info-soft p-3">
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    value={link}
                    aria-label="Candidate interview link"
                    onFocus={(event) => event.target.select()}
                    className="h-9 min-w-0 flex-1 rounded-btn border border-line bg-card px-3 text-[13px] text-ink"
                  />
                  <CopyLinkButton url={link} />
                </div>
                <p className="mt-1.5 text-xs text-info-ink">
                  Share this link with the candidate — it expires and works once.
                </p>
              </div>
            ) : null}

            {canManage ? (
              <InviteForm
                jobId={job.id}
                onInvited={(invitation) => {
                  refreshCandidates();
                  setLink(invitation.accept_url);
                }}
              />
            ) : null}

            <div>
              {invitationsLoading && !invitations ? (
                <SkeletonList rows={2} />
              ) : invitations && invitations.length > 0 ? (
                <ul className="space-y-2">
                  {invitations.map((invitation) => (
                    <InvitationRow
                      key={invitation.id}
                      invitation={invitation}
                      canManage={canManage}
                      onChanged={refreshCandidates}
                      onLink={setLink}
                    />
                  ))}
                </ul>
              ) : (
                <EmptyState
                  icon={<UserPlus className="h-6 w-6" aria-hidden />}
                  title="No candidates yet"
                  description="Invite someone above and share the magic link."
                  className="py-10"
                />
              )}
            </div>
          </CardContent>
        </Card>

        {canManage ? (
          <Card className="lg:col-span-2">
            <CardHeader
              title="Reviewers"
              description="Assigned reviewers can read this role's pipeline and record decisions; they cannot edit the job or invite candidates."
            />
            <CardContent>
              <ReviewersPanel job={job} onSaved={reload} />
            </CardContent>
          </Card>
        ) : null}

        <Card className="lg:col-span-2">
          <CardHeader
            title="Shortlist"
            description="Advisory ranking by score. Integrity is context, not a verdict — you make the call."
          />
          <CardContent>
            <ShortlistPanel
              jobId={job.id}
              reloadSignal={reviewSignal}
              onChanged={refreshCandidates}
            />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Pipeline analytics"
            description="Aggregate funnel and advisory score distribution for this role."
          />
          <CardContent>
            <AnalyticsPanel jobId={job.id} reloadSignal={reviewSignal} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Shadow mode"
            description="How often the advisory AI would have matched the decisions your team recorded. AI screening stays advisory — it never changes an outcome."
          />
          <CardContent>
            <ShadowPanel jobId={job.id} reloadSignal={reviewSignal} />
          </CardContent>
        </Card>
      </div>

      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete this job?"
        description="This removes the requisition. Invitations already sent are kept."
      >
        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={deleting}
            onClick={() => void onDelete()}
          >
            Delete job
          </Button>
        </div>
      </Modal>
    </div>
  );
}

interface InviteFormProps {
  jobId: string;
  onInvited: (invitation: Invitation) => void;
}

function InviteForm({ jobId, onInvited }: InviteFormProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [expiresDays, setExpiresDays] = useState("");
  const [extraMinutes, setExtraMinutes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setError("A candidate email is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const invitation = await invitationService.createInvitation({
        job_id: jobId,
        candidate_email: email.trim(),
        candidate_name: name.trim(),
        expires_in_days: expiresDays ? Number(expiresDays) : undefined,
        extra_minutes: extraMinutes ? Number(extraMinutes) : undefined,
      });
      setName("");
      setEmail("");
      setExpiresDays("");
      setExtraMinutes("");
      onInvited(invitation);
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-btn border border-line bg-surface p-4"
      noValidate
    >
      <h4 className="text-[13px] font-semibold text-ink">Invite a candidate</h4>
      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Input
          aria-label="Candidate name"
          placeholder="Candidate name (optional)"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Input
          aria-label="Candidate email"
          type="email"
          placeholder="candidate@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="w-40">
          <Field label="Link expires" htmlFor="invite-expires" optional>
            <select
              id="invite-expires"
              className={inputClasses}
              value={expiresDays}
              onChange={(event) => setExpiresDays(event.target.value)}
            >
              <option value="">Default</option>
              <option value="1">1 day</option>
              <option value="3">3 days</option>
              <option value="7">7 days</option>
              <option value="14">14 days</option>
            </select>
          </Field>
        </div>
        <div className="w-40">
          <Field label="Extra time" htmlFor="invite-extra" optional>
            <select
              id="invite-extra"
              className={inputClasses}
              value={extraMinutes}
              onChange={(event) => setExtraMinutes(event.target.value)}
            >
              <option value="">None</option>
              <option value="5">+5 min</option>
              <option value="10">+10 min</option>
              <option value="15">+15 min</option>
              <option value="30">+30 min</option>
            </select>
          </Field>
        </div>
        <Button type="submit" loading={submitting} className="mb-0.5">
          Send invite
        </Button>
      </div>
    </form>
  );
}

interface InvitationRowProps {
  invitation: Invitation;
  canManage: boolean;
  onChanged: () => void;
  onLink: (url: string) => void;
}

function InvitationRow({ invitation, canManage, onChanged, onLink }: InvitationRowProps) {
  const [busy, setBusy] = useState<"remind" | "revoke" | "extend" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [extendMinutes, setExtendMinutes] = useState("15");
  const [integrity, setIntegrity] = useState<IntegrityReport | null>(null);
  const [integrityOpen, setIntegrityOpen] = useState(false);
  const [integrityLoading, setIntegrityLoading] = useState(false);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [scorecardOpen, setScorecardOpen] = useState(false);
  const [scorecardLoading, setScorecardLoading] = useState(false);
  const [scorecardError, setScorecardError] = useState<string | null>(null);
  const [timelineOpen, setTimelineOpen] = useState(false);

  const openScorecard = async () => {
    setScorecardOpen(true);
    if (scorecard) return;
    setScorecardLoading(true);
    setScorecardError(null);
    try {
      setScorecard(await invitationService.getInvitationScorecard(invitation.id));
    } catch (caught) {
      setScorecardError(toApiError(caught).message);
    } finally {
      setScorecardLoading(false);
    }
  };

  const openIntegrity = async () => {
    setIntegrityOpen(true);
    if (integrity) return;
    setIntegrityLoading(true);
    setIntegrityError(null);
    try {
      setIntegrity(await invitationService.getInvitationIntegrity(invitation.id));
    } catch (caught) {
      setIntegrityError(toApiError(caught).message);
    } finally {
      setIntegrityLoading(false);
    }
  };

  const remind = async () => {
    setBusy("remind");
    setError(null);
    try {
      const updated = await invitationService.remindInvitation(invitation.id);
      if (updated.accept_url) onLink(updated.accept_url);
      onChanged();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  const extend = async () => {
    setBusy("extend");
    setError(null);
    try {
      await invitationService.extendInvitation(
        invitation.id,
        Number(extendMinutes),
      );
      onChanged();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  const revoke = async () => {
    setBusy("revoke");
    setError(null);
    try {
      await invitationService.revokeInvitation(invitation.id);
      onChanged();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setBusy(null);
    }
  };

  const revocable = invitation.status === "pending";
  const extendable =
    invitation.status === "pending" ||
    invitation.status === "started" ||
    invitation.status === "expired";
  const hasSession =
    invitation.status === "started" || invitation.status === "completed";

  return (
    <li className="rounded-btn border border-line px-3.5 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink">
            {invitation.candidate_name || invitation.candidate_email}
          </p>
          <p className="truncate text-xs text-ink-2">
            {invitation.candidate_email} · {invitation.round_minutes} min · expires{" "}
            {formatDate(invitation.expires_at)}
          </p>
        </div>
        <Badge tone={INVITATION_TONES[invitation.status]}>
          {INVITATION_LABELS[invitation.status]}
        </Badge>
        {hasSession ? (
          <Button
            variant="ghost"
            size="sm"
            icon={<ShieldCheck className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => void openIntegrity()}
          >
            Integrity
          </Button>
        ) : null}
        {hasSession ? (
          <Button
            variant="ghost"
            size="sm"
            icon={<Film className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => setTimelineOpen(true)}
          >
            Timeline
          </Button>
        ) : null}
        {invitation.status === "completed" ? (
          <Button
            variant="ghost"
            size="sm"
            icon={<Gauge className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => void openScorecard()}
          >
            Scorecard
          </Button>
        ) : null}
        {canManage && extendable ? (
          <div className="flex items-center gap-1.5">
            <select
              aria-label="Extra time to add"
              className={cx(inputClasses, "h-8 w-24 px-2 py-0 text-xs")}
              value={extendMinutes}
              onChange={(event) => setExtendMinutes(event.target.value)}
            >
              <option value="5">+5 min</option>
              <option value="10">+10 min</option>
              <option value="15">+15 min</option>
              <option value="30">+30 min</option>
            </select>
            <Button
              variant="ghost"
              size="sm"
              icon={<Clock className="h-3.5 w-3.5" aria-hidden />}
              loading={busy === "extend"}
              onClick={() => void extend()}
            >
              Extend
            </Button>
          </div>
        ) : null}
        <div className="flex items-center gap-1.5">
          {canManage && revocable ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                icon={<BellRing className="h-3.5 w-3.5" aria-hidden />}
                loading={busy === "remind"}
                onClick={() => void remind()}
              >
                Remind
              </Button>
              <Button
                variant="ghost"
                size="sm"
                loading={busy === "revoke"}
                onClick={() => void revoke()}
              >
                Revoke
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {error ? (
        <p className="mt-2 text-xs font-medium text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <Modal
        open={integrityOpen}
        onClose={() => setIntegrityOpen(false)}
        title="Integrity summary"
        description="Advisory signals only — a human always decides."
      >
        {integrityLoading ? (
          <p className="text-sm text-ink-2">Loading integrity summary…</p>
        ) : integrityError ? (
          <Alert tone="error">{integrityError}</Alert>
        ) : integrity ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge tone={INTEGRITY_LEVEL_TONES[integrity.level]}>
                {INTEGRITY_LEVEL_LABELS[integrity.level]}
              </Badge>
              <span className="text-sm font-semibold tabular-nums text-ink">
                Clean-session score {integrity.score}/100
              </span>
            </div>

            {integrity.recording_available ? (
              <p className="flex items-center gap-2 text-xs text-ink-2">
                <ShieldCheck className="h-3.5 w-3.5 text-brand" aria-hidden />
                Session recording available (
                {Math.round(integrity.recording_size_bytes / 1024 / 1024)} MB)
              </p>
            ) : null}

            {integrity.signals.length > 0 ? (
              <ul className="space-y-2">
                {integrity.signals.map((signal) => (
                  <li
                    key={signal.type}
                    className="flex items-center justify-between gap-3 text-[13px] text-ink"
                  >
                    <span className="min-w-0">{signal.label}</span>
                    <span className="tabular-nums text-ink-2">×{signal.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-ink-2">
                No notable signals during the session.
              </p>
            )}

            {integrity.moments.length > 0 ? (
              <div>
                <h5 className="text-[13px] font-semibold text-ink">Timeline</h5>
                <ul className="mt-2 space-y-1.5">
                  {integrity.moments.map((moment, index) => (
                    <li
                      key={`${moment.type}-${index}`}
                      className="flex items-center justify-between gap-3 text-xs text-ink-2"
                    >
                      <span className="min-w-0 truncate">{moment.label}</span>
                      <span className="tabular-nums">
                        {moment.at ? formatTime(moment.at) : "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {integrity.notes.length > 0 ? (
              <ul className="space-y-1 text-xs text-ink-3">
                {integrity.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        open={scorecardOpen}
        onClose={() => setScorecardOpen(false)}
        title="Competency scorecard"
        description="Advisory scoring with cited evidence — a human always decides."
      >
        {scorecardLoading ? (
          <p className="text-sm text-ink-2">Loading scorecard…</p>
        ) : scorecardError ? (
          <Alert tone="error">{scorecardError}</Alert>
        ) : scorecard ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={scorecard.meets_threshold ? "success" : "muted"}>
                {scorecard.meets_threshold ? "Meets threshold" : "Below threshold"}
              </Badge>
              <span className="text-sm font-semibold tabular-nums text-ink">
                Overall {scorecard.overall_score}/100
                {scorecard.threshold > 0 ? ` · threshold ${scorecard.threshold}` : ""}
              </span>
            </div>
            <p className="text-[13px] text-ink-2">{scorecard.recommendation}</p>

            <ul className="space-y-3">
              {scorecard.competencies.map((item) => (
                <li
                  key={item.competency}
                  className="rounded-btn border border-line px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate text-[13px] font-medium text-ink">
                      {item.competency}
                    </span>
                    <span className="tabular-nums text-[13px] text-ink-2">
                      {item.answered > 0 ? `${item.score}/100` : "Not assessed"}
                    </span>
                  </div>
                  {item.evidence.length > 0 ? (
                    <ul className="mt-1.5 space-y-1">
                      {item.evidence.flatMap((entry) =>
                        entry.quotes.map((quote) => (
                          <li
                            key={`${entry.question_id}-${quote}`}
                            className="text-xs italic text-ink-3"
                          >
                            &ldquo;{quote}&rdquo;
                          </li>
                        )),
                      )}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>

            {scorecard.strengths.length > 0 || scorecard.concerns.length > 0 ? (
              <p className="text-xs text-ink-3">
                {scorecard.strengths.length > 0
                  ? `Strengths: ${scorecard.strengths.join(", ")}. `
                  : ""}
                {scorecard.concerns.length > 0
                  ? `Concerns: ${scorecard.concerns.join(", ")}.`
                  : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <CandidateTimelineModal
        invitationId={invitation.id}
        candidateName={
          invitation.candidate_name || invitation.candidate_email
        }
        open={timelineOpen}
        onClose={() => setTimelineOpen(false)}
      />
    </li>
  );
}

const DECISION_OPTIONS: { value: Decision; label: string }[] = [
  { value: "pending", label: "No decision" },
  { value: "advance", label: "Advance" },
  { value: "hold", label: "Hold" },
  { value: "decline", label: "Decline" },
];

interface ShortlistPanelProps {
  jobId: string;
  reloadSignal: number;
  onChanged: () => void;
}

function ShortlistPanel({ jobId, reloadSignal, onChanged }: ShortlistPanelProps) {
  const { data, loading, error, reload } = useAsync(
    () => invitationService.getJobShortlist(jobId),
    [jobId, reloadSignal],
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const decide = async (entry: ShortlistEntry, decision: Decision) => {
    setBusyId(entry.invitation_id);
    setActionError(null);
    try {
      await invitationService.setInvitationDecision(entry.invitation_id, decision);
      reload();
      onChanged();
    } catch (caught) {
      setActionError(toApiError(caught).message);
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !data) return <SkeletonList rows={2} />;
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!data || data.length === 0) {
    return (
      <p className="text-[13px] text-ink-2">
        No candidates yet — invite someone to build the shortlist.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {actionError ? <Alert tone="error">{actionError}</Alert> : null}
      <div className="flex justify-end">
        <CompareCandidatesButton entries={data} />
      </div>
      <ol className="space-y-2">
        {data.map((entry, index) => (
          <li
            key={entry.invitation_id}
            className="rounded-btn border border-line px-3.5 py-3"
          >
            <div className="flex flex-wrap items-center gap-3">
              <span className="w-5 shrink-0 text-sm font-semibold tabular-nums text-ink-3">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">
                  {entry.candidate_name || entry.candidate_email}
                </p>
                <p className="truncate text-xs text-ink-2">
                  {entry.status === "completed"
                    ? `${entry.overall_score}/100${
                        entry.threshold > 0 ? ` · threshold ${entry.threshold}` : ""
                      }${
                        entry.percentile !== null
                          ? ` · ${entry.percentile}th pct`
                          : ""
                      }`
                    : "Not completed"}
                </p>
              </div>
              {entry.integrity_level ? (
                <Badge tone={INTEGRITY_LEVEL_TONES[entry.integrity_level]}>
                  {INTEGRITY_LEVEL_LABELS[entry.integrity_level]}
                </Badge>
              ) : null}
              <select
                aria-label={`Decision for ${entry.candidate_email}`}
                className={cx(inputClasses, "h-8 w-32 px-2 py-0 text-xs")}
                value={entry.decision}
                disabled={busyId === entry.invitation_id}
                onChange={(event) =>
                  void decide(entry, event.target.value as Decision)
                }
              >
                {DECISION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

interface AnalyticsPanelProps {
  jobId: string;
  reloadSignal: number;
}

function AnalyticsPanel({ jobId, reloadSignal }: AnalyticsPanelProps) {
  const { data, loading, error } = useAsync(
    () => invitationService.getJobAnalytics(jobId),
    [jobId, reloadSignal],
  );
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const runExport = async (
    fetcher: () => Promise<Blob>,
    filename: string,
  ) => {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await fetcher();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setExportError(toApiError(caught).message);
    } finally {
      setExporting(false);
    }
  };

  if (loading && !data) return <SkeletonList rows={2} />;
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!data) return null;

  const stats: { label: string; value: string | number }[] = [
    { label: "Invited", value: data.total_invited },
    { label: "In progress", value: data.in_progress },
    { label: "Completed", value: data.completed },
    { label: "Expired / revoked", value: data.expired + data.revoked },
    { label: "Completion rate", value: `${data.completion_rate}%` },
    { label: "Pass rate", value: `${data.pass_rate}%` },
    {
      label: "Average score",
      value: data.completed ? data.average_score.toFixed(1) : "—",
    },
    {
      label: "Median score",
      value: data.completed ? data.median_score.toFixed(1) : "—",
    },
  ];
  const maxBucket = Math.max(
    1,
    ...data.score_distribution.map((bucket) => bucket.count),
  );

  return (
    <div className="space-y-5">
      {exportError ? <Alert tone="error">{exportError}</Alert> : null}

      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          loading={exporting}
          icon={<Download className="h-3.5 w-3.5" aria-hidden />}
          onClick={() =>
            void runExport(
              () => invitationService.downloadJobCandidatesPdf(jobId),
              "screening-summary.pdf",
            )
          }
        >
          Export PDF
        </Button>
        <Button
          variant="outline"
          size="sm"
          loading={exporting}
          icon={<Download className="h-3.5 w-3.5" aria-hidden />}
          onClick={() =>
            void runExport(
              () => invitationService.downloadJobCandidatesCsv(jobId),
              "candidates.csv",
            )
          }
        >
          Export CSV
        </Button>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-btn border border-line px-3 py-2.5"
          >
            <dt className="text-xs text-ink-2">{stat.label}</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>

      <div>
        <h5 className="text-[13px] font-semibold text-ink">
          Score distribution
        </h5>
        <ul className="mt-2 space-y-1.5">
          {data.score_distribution.map((bucket) => (
            <li key={bucket.label} className="flex items-center gap-3 text-xs">
              <span className="w-14 shrink-0 tabular-nums text-ink-2">
                {bucket.label}
              </span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-mist">
                <span
                  className="block h-full rounded-full bg-brand"
                  style={{ width: `${(bucket.count / maxBucket) * 100}%` }}
                />
              </span>
              <span className="w-6 shrink-0 text-right tabular-nums text-ink-2">
                {bucket.count}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
        <span>
          Decisions:{" "}
          {DECISION_OPTIONS.map((option) => (
            <span key={option.value} className="mr-2 tabular-nums">
              {option.label} {data.decisions[option.value] ?? 0}
            </span>
          ))}
        </span>
        <span>
          Integrity:{" "}
          {Object.entries(data.integrity_distribution)
            .filter(([, count]) => count > 0)
            .map(([level, count]) => (
              <span key={level} className="mr-2 tabular-nums">
                {INTEGRITY_LEVEL_LABELS[
                  level as keyof typeof INTEGRITY_LEVEL_LABELS
                ] ?? level}{" "}
                {count}
              </span>
            ))}
        </span>
      </div>
    </div>
  );
}

const BIAS_TONES: Record<BiasVerdict, BadgeTone> = {
  aligned: "success",
  lenient: "warning",
  strict: "warning",
};

const BIAS_LABELS: Record<BiasVerdict, string> = {
  aligned: "Aligned with the panel",
  lenient: "The AI leans lenient",
  strict: "The AI leans strict",
};

const DISAGREEMENT_LABELS: Record<string, string> = {
  ai_lenient: "AI advanced, held by you",
  ai_strict: "AI held, advanced by you",
};

interface ShadowPanelProps {
  jobId: string;
  reloadSignal: number;
}

function ShadowPanel({ jobId, reloadSignal }: ShadowPanelProps) {
  const { data, loading, error } = useAsync<ShadowReport>(
    () => invitationService.getJobShadow(jobId),
    [jobId, reloadSignal],
  );

  if (loading && !data) return <SkeletonList rows={2} />;
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!data) return null;

  if (data.compared === 0) {
    const waiting = [
      data.excluded_awaiting_decision
        ? `${data.excluded_awaiting_decision} awaiting a decision`
        : null,
      data.excluded_no_threshold
        ? `${data.excluded_no_threshold} without a pass threshold`
        : null,
      data.excluded_not_completed
        ? `${data.excluded_not_completed} not completed`
        : null,
    ].filter(Boolean);
    return (
      <p className="text-sm text-ink-2">
        No decided candidates to compare yet
        {waiting.length ? ` (${waiting.join(", ")})` : ""}. Record decisions on
        the shortlist to see how the advisory AI lines up with your team.
      </p>
    );
  }

  const quadrants: { label: string; value: number; agree: boolean }[] = [
    { label: "Both advanced", value: data.agreed_advance, agree: true },
    { label: "AI advanced, you held", value: data.ai_lenient, agree: false },
    { label: "AI held, you advanced", value: data.ai_strict, agree: false },
    { label: "Both held", value: data.agreed_review, agree: true },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-3xl font-semibold tabular-nums text-ink">
          {data.agreement_rate.toFixed(1)}%
        </span>
        <span className="text-sm text-ink-2">
          agreement across {data.compared} decided candidate
          {data.compared === 1 ? "" : "s"}
        </span>
        <Badge tone={BIAS_TONES[data.bias]}>{BIAS_LABELS[data.bias]}</Badge>
      </div>

      {!data.sufficient_sample ? (
        <p className="text-xs text-ink-2">
          Fewer than 10 decided candidates — read this rate as indicative, not
          conclusive.
        </p>
      ) : null}

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "AI advance rate", value: `${data.advanced_rate_ai}%` },
          { label: "Human advance rate", value: `${data.advanced_rate_human}%` },
          { label: "Agreed", value: data.agreed },
          { label: "Disagreed", value: data.ai_lenient + data.ai_strict },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-btn border border-line px-3 py-2.5"
          >
            <dt className="text-xs text-ink-2">{stat.label}</dt>
            <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>

      <div>
        <h5 className="text-[13px] font-semibold text-ink">Agreement grid</h5>
        <ul className="mt-2 grid grid-cols-2 gap-2">
          {quadrants.map((quadrant) => (
            <li
              key={quadrant.label}
              className="flex items-center justify-between rounded-btn border border-line px-3 py-2 text-xs"
            >
              <span className="text-ink-2">{quadrant.label}</span>
              <span
                className={cx(
                  "tabular-nums font-semibold",
                  quadrant.agree ? "text-ink" : "text-warning",
                )}
              >
                {quadrant.value}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {data.disagreements.length ? (
        <div>
          <h5 className="text-[13px] font-semibold text-ink">
            Disagreements
          </h5>
          <ul className="mt-2 divide-y divide-line">
            {data.disagreements.map((item) => (
              <li
                key={item.invitation_id}
                className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs"
              >
                <span className="font-medium text-ink">
                  {item.candidate_name || "Candidate"}
                </span>
                <span className="text-ink-2">
                  {DISAGREEMENT_LABELS[item.direction] ?? item.direction}
                </span>
                <span className="tabular-nums text-ink-2">
                  score {item.overall_score.toFixed(0)} vs threshold{" "}
                  {item.threshold.toFixed(0)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-xs text-ink-2">
          Every decided candidate so far matches the advisory recommendation.
        </p>
      )}

      <p className="text-xs text-ink-2">
        Excluded from the comparison:{" "}
        {[
          `${data.excluded_awaiting_decision} awaiting a decision`,
          `${data.excluded_no_threshold} without a threshold`,
          `${data.excluded_not_completed} not completed`,
        ].join(", ")}
        .
      </p>
    </div>
  );
}
