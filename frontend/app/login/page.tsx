"use client";

import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";

import { ArrowRight } from "lucide-react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { GuestGuard } from "@/components/auth/auth-guard";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, Input, PasswordInput } from "@/components/ui/input";
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import { safeNextPath } from "@/lib/utils";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    email?: string;
    password?: string;
  }>({});

  const validate = () => {
    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errors.email = "Email is required";
    } else if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      errors.email = "Enter a valid email address";
    }
    if (!password) errors.password = "Password is required";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      router.replace(safeNextPath(searchParams.get("next")));
    } catch (caught) {
      const apiError = toApiError(caught);
      setError(
        apiError.status === 401
          ? "That email and password combination doesn't match an account."
          : apiError.message,
      );
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5" noValidate>
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Field label="Email" htmlFor="email" required error={fieldErrors.email}>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          invalid={Boolean(fieldErrors.email)}
          aria-invalid={Boolean(fieldErrors.email)}
          aria-describedby={fieldErrors.email ? "email-error" : undefined}
          onChange={(event) => setEmail(event.target.value)}
        />
      </Field>

      <Field
        label="Password"
        htmlFor="password"
        required
        error={fieldErrors.password}
      >
        <PasswordInput
          id="password"
          name="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          invalid={Boolean(fieldErrors.password)}
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={fieldErrors.password ? "password-error" : undefined}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>

      <Button
        type="submit"
        size="lg"
        className="w-full"
        loading={submitting}
        icon={<ArrowRight className="h-4 w-4" aria-hidden />}
      >
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <GuestGuard>
      <AuthLayout
        title="Welcome back"
        subtitle="Sign in to continue your interview preparation."
        footer={
          <>
            New here?{" "}
            <Link
              href="/register"
              className="font-medium text-brand hover:text-brand-hover"
            >
              Create an account
            </Link>
          </>
        }
      >
        <Suspense>
          <LoginForm />
        </Suspense>
      </AuthLayout>
    </GuestGuard>
  );
}
