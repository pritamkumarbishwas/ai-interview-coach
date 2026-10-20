"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { FullScreenLoader } from "@/components/ui/loading";
import { useAuth } from "@/hooks/use-auth";
import type { Role } from "@/types";

/**
 * Client-side role gate for staff-only pages. The API enforces the same rule,
 * so this is purely a UX shortcut (and keeps a stray recruit from seeing an
 * empty page of 403s).
 */
export function RequireRole({
  roles,
  children,
  redirectTo = "/dashboard",
}: {
  roles: Role[];
  children: ReactNode;
  redirectTo?: string;
}) {
  const { user, status } = useAuth();
  const router = useRouter();

  const allowed = Boolean(user && roles.includes(user.role));

  useEffect(() => {
    if (status === "authenticated" && user && !roles.includes(user.role)) {
      router.replace(redirectTo);
    }
  }, [status, user, roles, router, redirectTo]);

  if (status !== "authenticated" || !user) {
    return <FullScreenLoader label="Checking access" />;
  }

  if (!allowed) {
    return <FullScreenLoader label="Redirecting" />;
  }

  return <>{children}</>;
}
