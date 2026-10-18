"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ArrowRight } from "lucide-react";

import { Logo } from "@/components/layout/logo";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { toApiError } from "@/lib/api";
import * as staffService from "@/services/staff";

function AcceptForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) {
      setError("This invitation link is missing its token.");
      return;
    }
    if (!name.trim()) {
      setError("Please enter your name.");
      return;
    }
    if (password.length < 8) {
      setError("Use at least 8 characters for your password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await staffService.acceptStaffInvitation({
        token,
        name: name.trim(),
        password,
      });
      router.replace("/jobs");
    } catch (caught) {
      const apiError = toApiError(caught);
      setError(
        apiError.status === 400 || apiError.status === 404
          ? "This invitation is invalid or has expired. Ask an admin to re-invite you."
          : apiError.message,
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6 py-12">
      <div className="w-full max-w-md">
        <Logo className="mb-8" />
        <h1 className="text-2xl font-bold tracking-tight text-ink">
          Accept your invitation
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
          Set your name and password to join the workspace.
        </p>

        <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
          {error ? <Alert tone="error">{error}</Alert> : null}

          <Field label="Full name" htmlFor="accept-name" required>
            <Input
              id="accept-name"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Jordan Lee"
            />
          </Field>

          <Field
            label="Password"
            htmlFor="accept-password"
            required
            hint="At least 8 characters."
          >
            <PasswordInput
              id="accept-password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          <Field label="Confirm password" htmlFor="accept-confirm" required>
            <PasswordInput
              id="accept-confirm"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </Field>

          <Button
            type="submit"
            size="lg"
            className="w-full"
            loading={submitting}
            icon={<ArrowRight className="h-4 w-4" aria-hidden />}
          >
            {submitting ? "Joining…" : "Join workspace"}
          </Button>
        </form>
      </div>
    </div>
  );
}

export default function StaffAcceptPage() {
  return (
    <Suspense>
      <AcceptForm />
    </Suspense>
  );
}
