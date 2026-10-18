"use client";

import { useState, type FormEvent } from "react";

import { Check, Copy, MailPlus, UserPlus, Users } from "lucide-react";

import { RequireRole } from "@/components/auth/require-role";
import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Input, inputClasses } from "@/components/ui/input";
import { SkeletonList } from "@/components/ui/loading";
import { Modal } from "@/components/ui/modal";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import { ADMIN_ROLES, ROLE_LABELS, STAFF_ROLES } from "@/lib/recruiting";
import { formatDate } from "@/lib/utils";
import * as staffService from "@/services/staff";
import type { Role, StaffInvitationStatus } from "@/types";

const INVITATION_TONES: Record<StaffInvitationStatus, BadgeTone> = {
  pending: "warning",
  accepted: "success",
  revoked: "muted",
};

export default function TeamPage() {
  return (
    <RequireRole roles={ADMIN_ROLES}>
      <Team />
    </RequireRole>
  );
}

function Team() {
  const {
    data: users,
    loading,
    error,
    reload,
  } = useAsync(() => staffService.listStaff(), []);
  const {
    data: invitations,
    loading: invitationsLoading,
    reload: reloadInvitations,
  } = useAsync(() => staffService.listStaffInvitations(), []);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [link, setLink] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
            Team
          </h2>
          <p className="mt-1 text-sm text-ink-2">
            Manage staff access. Candidates never appear here — they enter by
            magic link.
          </p>
        </div>
        <Button
          className="ml-auto"
          icon={<UserPlus className="h-4 w-4" aria-hidden />}
          onClick={() => setInviteOpen(true)}
        >
          Invite staff
        </Button>
      </header>

      {link ? (
        <div className="rounded-btn border border-[#f8dcb8] bg-ai p-3">
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={link}
              aria-label="Staff invitation link"
              onFocus={(event) => event.target.select()}
              className="h-9 min-w-0 flex-1 rounded-btn border border-line bg-card px-3 text-[13px] text-ink"
            />
            <CopyButton url={link} />
          </div>
          <p className="mt-1.5 text-xs text-[#8a5310]">
            Share this invitation link with the new team member.
          </p>
        </div>
      ) : null}

      {error ? (
        <Alert tone="error">
          Couldn&apos;t load the team: {error.message}
          <button
            type="button"
            onClick={reload}
            className="ml-2 font-medium underline"
          >
            Retry
          </button>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Staff" description="Roles and access." />
          <CardContent>
            {loading && !users ? (
              <SkeletonList rows={3} />
            ) : users && users.length > 0 ? (
              <ul className="space-y-2">
                {users.map((user) => (
                  <UserRow key={user.id} user={user} onChanged={reload} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<Users className="h-6 w-6" aria-hidden />}
                title="No staff yet"
                description="Invite your first teammate."
                className="py-8"
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Pending invitations"
            description="Unaccepted staff invitations."
          />
          <CardContent>
            {invitationsLoading && !invitations ? (
              <SkeletonList rows={2} />
            ) : invitations && invitations.length > 0 ? (
              <ul className="space-y-2">
                {invitations.map((invitation) => (
                  <li
                    key={invitation.id}
                    className="flex flex-wrap items-center gap-3 rounded-btn border border-line px-3.5 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {invitation.email}
                      </p>
                      <p className="text-xs text-ink-2">
                        {ROLE_LABELS[invitation.role]} · expires{" "}
                        {formatDate(invitation.expires_at)}
                      </p>
                    </div>
                    <Badge tone={INVITATION_TONES[invitation.status]}>
                      {invitation.status}
                    </Badge>
                    {invitation.status === "pending" ? (
                      <RevokeButton
                        id={invitation.id}
                        onDone={reloadInvitations}
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<MailPlus className="h-6 w-6" aria-hidden />}
                title="No pending invitations"
                description="Invited teammates accept via a secure link."
                className="py-8"
              />
            )}
          </CardContent>
        </Card>
      </div>

      <InviteStaffModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onInvited={(acceptUrl) => {
          setInviteOpen(false);
          reloadInvitations();
          if (acceptUrl) setLink(acceptUrl);
        }}
      />
    </div>
  );
}

function CopyButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
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

function UserRow({
  user,
  onChanged,
}: {
  user: { id: string; name: string; email: string; role: Role };
  onChanged: () => void;
}) {
  const [role, setRole] = useState<Role>(user.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onChange = async (next: Role) => {
    const previous = role;
    setRole(next);
    setBusy(true);
    setError(null);
    try {
      await staffService.updateStaffRole(user.id, next);
      onChanged();
    } catch (caught) {
      setRole(previous);
      setError(toApiError(caught).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="rounded-btn border border-line px-3.5 py-3">
      <div className="flex items-center gap-3">
        <Avatar name={user.name || user.email} size="sm" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink">
            {user.name || user.email}
          </p>
          <p className="truncate text-xs text-ink-2">{user.email}</p>
        </div>
        <select
          aria-label={`Role for ${user.email}`}
          className={`${inputClasses} h-9 w-40 py-0`}
          value={role}
          disabled={busy}
          onChange={(event) => void onChange(event.target.value as Role)}
        >
          {STAFF_ROLES.map((value) => (
            <option key={value} value={value}>
              {ROLE_LABELS[value]}
            </option>
          ))}
        </select>
      </div>
      {error ? (
        <p className="mt-2 text-xs font-medium text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function RevokeButton({ id, onDone }: { id: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const onRevoke = async () => {
    setBusy(true);
    try {
      await staffService.revokeStaffInvitation(id);
      onDone();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button
      variant="ghost"
      size="sm"
      loading={busy}
      onClick={() => void onRevoke()}
    >
      Revoke
    </Button>
  );
}

interface InviteStaffModalProps {
  open: boolean;
  onClose: () => void;
  onInvited: (acceptUrl: string | null) => void;
}

function InviteStaffModal({ open, onClose, onInvited }: InviteStaffModalProps) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("recruiter");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) {
      setError("An email is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const invitation = await staffService.createStaffInvitation({
        email: email.trim(),
        role,
        name: name.trim(),
      });
      setEmail("");
      setName("");
      setRole("recruiter");
      onInvited(invitation.accept_url);
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
      title="Invite a teammate"
      description="They join with the role you choose."
      className="max-w-lg"
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}

        <Field label="Name" htmlFor="staff-name" optional>
          <Input
            id="staff-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Jordan Lee"
          />
        </Field>

        <Field label="Email" htmlFor="staff-email" required>
          <Input
            id="staff-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="teammate@example.com"
          />
        </Field>

        <Field label="Role" htmlFor="staff-role">
          <select
            id="staff-role"
            className={inputClasses}
            value={role}
            onChange={(event) => setRole(event.target.value as Role)}
          >
            {STAFF_ROLES.map((value) => (
              <option key={value} value={value}>
                {ROLE_LABELS[value]}
              </option>
            ))}
          </select>
        </Field>

        <div className="flex items-center justify-end gap-3 pt-1">
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            Send invitation
          </Button>
        </div>
      </form>
    </Modal>
  );
}
