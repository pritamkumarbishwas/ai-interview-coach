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
}: {
  roles: Role[];
  children: ReactNode;
}) {
  const { user, status } = useAuth();
  const router = useRouter();

  const allowed = Boolean(user && roles.includes(user.role));

  useEffect(() => {
    if (status === "authenticated" && user && !roles.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [status, user, roles, router]);

  if (status !== "authenticated" || !user) {
    return <FullScreenLoader label="Checking access" />;
  }

  if (!allowed) {
    return <FullScreenLoader label="Redirecting to your dashboard" />;
  }

  return <>{children}</>;
}
