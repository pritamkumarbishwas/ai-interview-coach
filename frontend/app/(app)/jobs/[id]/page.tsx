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
import { toApiError } from "@/lib/api";
import {
  INTEGRITY_LEVEL_LABELS,
  INTEGRITY_LEVEL_TONES,
  JOB_STATUS_LABELS,
  JOB_STATUS_TONES,
  STAFF_ROLES,
} from "@/lib/recruiting";
import { cx, formatDate } from "@/lib/utils";import * as invitationService from "@/services/invitations";
import * as jobService from "@/services/jobs";
import * as templateService from "@/services/templates";
import type {
  Decision,
  IntegrityReport,
  Invitation,
  InvitationStatus,
  JobStatus,
  Scorecard,
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

  const {
    data: job,
    loading,
    error,
    reload,
  } = useAsync(() => jobService.getJob(params.id), [params.id]);
  const { data: templates } = useAsync(() => templateService.listTemplates(), []);
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
          <CardHeader title="Job details" description="Edit the requisition." />
          <CardContent>
            {form ? (
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
            description="Invite candidates by magic link."
          />
          <CardContent className="space-y-5">
            {link ? (
              <div className="rounded-btn border border-[#f8dcb8] bg-ai p-3">
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
                <p className="mt-1.5 text-xs text-[#8a5310]">
                  Share this link with the candidate — it expires and works once.
                </p>
              </div>
            ) : null}

            <InviteForm
              jobId={job.id}
              onInvited={(invitation) => {
                refreshCandidates();
                setLink(invitation.accept_url);
              }}
            />

            <div>
              {invitationsLoading && !invitations ? (
                <SkeletonList rows={2} />
              ) : invitations && invitations.length > 0 ? (
                <ul className="space-y-2">
                  {invitations.map((invitation) => (
                    <InvitationRow
                      key={invitation.id}
                      invitation={invitation}
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
  onChanged: () => void;
  onLink: (url: string) => void;
}

function InvitationRow({ invitation, onChanged, onLink }: InvitationRowProps) {
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
        {extendable ? (
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
          {revocable ? (
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
                        {moment.at ? new Date(`${moment.at}Z`).toLocaleTimeString() : "—"}
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
