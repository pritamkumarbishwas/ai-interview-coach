"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { FullScreenLoader } from "@/components/ui/loading";
import { useAuth } from "@/hooks/use-auth";
import { safeNextPath } from "@/lib/utils";

function nextParam(pathname: string): string {
  return encodeURIComponent(pathname);
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(`/login?next=${nextParam(pathname)}`);
    }
  }, [status, router, pathname]);

  if (status === "loading") {
    return <FullScreenLoader label="Preparing your workspace" />;
  }

  if (status === "unauthenticated") {
    return <FullScreenLoader label="Redirecting to sign in" />;
  }

  return <>{children}</>;
}

export function GuestGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      const params = new URLSearchParams(window.location.search);
      router.replace(safeNextPath(params.get("next")));
    }
  }, [status, router]);

  // While the session is still being checked we show the form right away —
  // only an already-signed-in visitor gets swapped out for the redirect.
  if (status === "authenticated") {
    return <FullScreenLoader label="Taking you to your dashboard" />;
  }

  return <>{children}</>;
}
