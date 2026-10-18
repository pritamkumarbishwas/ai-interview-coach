"use client";

import { ScrollText } from "lucide-react";

import { RequireRole } from "@/components/auth/require-role";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonList } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { ADMIN_ROLES } from "@/lib/recruiting";
import { formatDateTime, titleCase } from "@/lib/utils";
import * as auditService from "@/services/audit";

export default function AuditPage() {
  return (
    <RequireRole roles={ADMIN_ROLES}>
      <Audit />
    </RequireRole>
  );
}

function Audit() {
  const { data: logs, loading, error, reload } = useAsync(
    () => auditService.listAuditLogs(),
    [],
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">
          Audit log
        </h2>
        <p className="mt-1 text-sm text-ink-2">
          Recent privileged actions across the workspace.
        </p>
      </div>

      {error ? (
        <Alert tone="error">
          Couldn&apos;t load the audit log: {error.message}
          <button
            type="button"
            onClick={reload}
            className="ml-2 font-medium underline"
          >
            Retry
          </button>
        </Alert>
      ) : null}

      {loading && !logs ? (
        <SkeletonList rows={5} />
      ) : logs && logs.length > 0 ? (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y divide-line">
              {logs.map((log) => (
                <li key={log.id} className="flex items-center gap-4 px-5 py-3.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-ink">
                      {titleCase(log.action)}
                    </p>
                    <p className="truncate text-xs text-ink-2">
                      {log.target_type || "—"}
                      {log.target_id ? ` · ${log.target_id}` : ""}
                      {log.actor_id ? ` · by ${log.actor_id}` : ""}
                    </p>
                  </div>
                  <Badge tone="neutral">{log.action.split(".")[0]}</Badge>
                  <span className="hidden shrink-0 text-xs text-ink-3 sm:block">
                    {formatDateTime(log.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={<ScrollText className="h-6 w-6" aria-hidden />}
          title="No audit events yet"
          description="Actions like creating jobs, inviting staff, and reviewing candidates appear here."
          action={
            <Button variant="outline" onClick={reload}>
              Refresh
            </Button>
          }
        />
      )}
    </div>
  );
}
