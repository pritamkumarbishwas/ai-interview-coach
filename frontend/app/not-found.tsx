import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-6 text-center">
      <p className="text-5xl font-bold tracking-tight text-brand">404</p>
      <h1 className="text-lg font-semibold text-ink">
        This page doesn&apos;t exist
      </h1>
      <p className="max-w-sm text-sm text-ink-2">
        The link may be broken, or the page may have moved.
      </p>
      <div className="flex items-center gap-3">
        <ButtonLink href="/dashboard">Back to dashboard</ButtonLink>
        <Link
          href="/interviews"
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          My interviews
        </Link>
      </div>
    </div>
  );
}
