"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { ArrowRight } from "lucide-react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { GuestGuard } from "@/components/auth/auth-guard";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import { cx } from "@/lib/utils";

function passwordStrength(password: string): {
  label: string;
  percent: number;
  color: string;
} {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^\w\s]/.test(password)) score += 1;

  if (score <= 1) return { label: "Weak", percent: 25, color: "bg-danger" };
  if (score <= 3) return { label: "Fair", percent: 60, color: "bg-warning" };
  return { label: "Strong", percent: 100, color: "bg-success" };
}

function RegisterForm() {
  const router = useRouter();
  const { register } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const strength = passwordStrength(password);

  const validate = () => {
    const errors: Record<string, string> = {};
    if (!name.trim()) errors.name = "Name is required";
    if (!email.trim()) {
      errors.email = "Email is required";
    } else if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      errors.email = "Enter a valid email address";
    }
    if (password.length < 8) errors.password = "Use at least 8 characters";
    if (confirm !== password) errors.confirm = "Passwords don't match";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim(),
        password,
      });
      router.replace("/dashboard");
    } catch (caught) {
      const apiError = toApiError(caught);
      setError(
        apiError.status === 409
          ? "An account with this email already exists. Try signing in instead."
          : apiError.message,
      );
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Field label="Full name" htmlFor="name" required error={fieldErrors.name}>
        <Input
          id="name"
          name="name"
          autoComplete="name"
          placeholder="Jane Doe"
          value={name}
          invalid={Boolean(fieldErrors.name)}
          onChange={(event) => setName(event.target.value)}
        />
      </Field>

      <Field label="Email" htmlFor="email" required error={fieldErrors.email}>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          invalid={Boolean(fieldErrors.email)}
          onChange={(event) => setEmail(event.target.value)}
        />
      </Field>

      <Field
        label="Password"
        htmlFor="password"
        required
        error={fieldErrors.password}
        hint="At least 8 characters."
      >
        <PasswordInput
          id="password"
          name="password"
          autoComplete="new-password"
          placeholder="••••••••"
          value={password}
          invalid={Boolean(fieldErrors.password)}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>

      {password ? (
        <div className="flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-mist">
            <div
              className={cx(
                "h-full rounded-full transition-all",
                strength.color,
              )}
              style={{ width: `${strength.percent}%` }}
            />
          </div>
          <span className="w-12 text-right text-xs font-medium text-ink-2">
            {strength.label}
          </span>
        </div>
      ) : null}

      <Field
        label="Confirm password"
        htmlFor="confirm"
        required
        error={fieldErrors.confirm}
      >
        <PasswordInput
          id="confirm"
          name="confirm"
          autoComplete="new-password"
          placeholder="••••••••"
          value={confirm}
          invalid={Boolean(fieldErrors.confirm)}
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
        {submitting ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}

export default function RegisterPage() {
  return (
    <GuestGuard>
      <AuthLayout
        title="Create your account"
        subtitle="Start practicing interviews tailored to your dream role."
        footer={
          <>
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-medium text-brand hover:text-brand-hover"
            >
              Sign in
            </Link>
          </>
        }
      >
        <RegisterForm />
      </AuthLayout>
    </GuestGuard>
  );
}
