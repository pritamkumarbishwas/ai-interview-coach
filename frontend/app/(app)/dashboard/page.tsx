"use client";

import Link from "next/link";

import {
  ArrowRight,
  ChevronRight,
  CircleCheck,
  Mic,
  Sparkles,
  Target,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";

import { useAsync } from "@/hooks/use-async";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonCard } from "@/components/ui/loading";
import { StatCard } from "@/components/ui/stat-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAuth } from "@/hooks/use-auth";
import {
  STATUS_LABELS,
  TYPE_LABELS,
  TYPE_TONES,
} from "@/lib/interview";
import { formatDate, greeting } from "@/lib/utils";
import { getDashboardStats } from "@/services/dashboard";

const ONBOARDING_STEPS = [
  {
    title: "Upload your resume",
    text: "PDF or DOCX — we extract your skills and experience.",
    href: "/resumes",
  },
  {
    title: "Add a job description",
    text: "Paste the role you are targeting so questions match it.",
    href: "/job-descriptions",
  },
  {
    title: "Start a mock interview",
    text: "Answer questions, get AI feedback, and see your report.",
    href: "/practice",
  },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const name = (user?.name ?? "").split(" ")[0];

  const { data: stats, loading, error, reload } = useAsync(
    getDashboardStats,
    [],
  );

  if (loading && !stats) {
    return (
      <div className="space-y-6">
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <SkeletonCard key={index} />
          ))}
        </section>
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl py-16">
        <Alert tone="error">
          {error.message || "Could not load your dashboard."}
        </Alert>
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={reload}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  const recent = stats?.recent ?? [];
  const strongTopics = stats?.strong_topics ?? [];
  const weakTopics = stats?.weak_topics ?? [];

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-ink-2">
            {greeting()}
            {name ? `, ${name}` : ""} 👋
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink lg:text-[28px]">
            Ready for your next interview?
          </h1>
          <p className="mt-1.5 max-w-xl text-sm text-ink-2">
            Practice with an AI interviewer, get scored on observable
            dimensions, and improve with every answer.
          </p>
        </div>
        <div className="flex gap-2.5">
          <ButtonLink href="/practice" variant="primary" icon={<Mic className="h-4 w-4" />}>
            Start Interview
          </ButtonLink>
          <ButtonLink href="/interviews" variant="outline">
            My Interviews
          </ButtonLink>
        </div>
      </section>

      <section
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Overview statistics"
      >
        <StatCard
          label="Total Interviews"
          value={stats?.interviews_total ?? 0}
          icon={<Target className="h-4 w-4" />}
          hint={`${stats?.interviews_completed ?? 0} completed`}
        />
        <StatCard
          label="Average Score"
          value={
            stats?.average_score !== null && stats?.average_score !== undefined
              ? `${stats.average_score}%`
              : "—"
          }
          icon={<TrendingUp className="h-4 w-4" />}
          hint="across completed reports"
        />
        <StatCard
          label="Questions Answered"
          value={stats?.questions_answered ?? 0}
          icon={<Sparkles className="h-4 w-4" />}
        />
        <StatCard
          label="In Progress"
          value={stats?.interviews_in_progress ?? 0}
          icon={<ArrowRight className="h-4 w-4" />}
          hint="resumable anytime"
        />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent Interviews"
            actions={
              <Link
                href="/interviews"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand transition-colors hover:text-brand-hover"
              >
                View all
                <ChevronRight className="h-4 w-4" aria-hidden />
              </Link>
            }
          />
          <CardContent className="p-0">
            {recent.length === 0 ? (
              <div className="px-6 py-10">
                <EmptyState
                  title="No interviews yet"
                  description="Start your first practice interview and it will show up here."
                  action={
                    <ButtonLink href="/practice" variant="primary">
                      Start Interview
                    </ButtonLink>
                  }
                />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-3">
                      <th scope="col" className="px-6 py-3 font-medium">
                        Role
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Type
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Score
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Date
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-3">
                        <span className="sr-only">Open</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((item) => (
                      <tr
                        key={item.id}
                        className="border-b border-line last:border-0 transition-colors hover:bg-surface"
                      >
                        <td className="px-6 py-3.5">
                          <span className="font-medium text-ink">
                            {item.role}
                          </span>
                        </td>
                        <td className="px-4 py-3.5">
                          <Badge tone={TYPE_TONES[item.type]}>
                            {TYPE_LABELS[item.type]}
                          </Badge>
                        </td>
                        <td className="px-4 py-3.5">
                          {item.score !== null ? (
                            <span className="font-semibold tabular-nums text-ink">
                              {item.score}%
                            </span>
                          ) : (
                            <span className="text-ink-3">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-ink-2">
                          {formatDate(item.created_at)}
                        </td>
                        <td className="px-4 py-3.5">
                          <StatusBadge status={item.status} />
                          <span className="sr-only">
                            {STATUS_LABELS[item.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          <Link
                            href={
                              item.status === "completed"
                                ? `/interviews/${item.id}/result`
                                : `/interviews/${item.id}`
                            }
                            className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand-50"
                          >
                            {item.status === "completed" ? "Report" : "Open"}
                            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Strong topics" />
            <CardContent>
              {strongTopics.length === 0 ? (
                <p className="text-sm text-ink-2">
                  Complete an interview to see where you shine.
                </p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {strongTopics.map((topic) => (
                    <li
                      key={topic}
                      className="inline-flex items-center gap-1.5 rounded-full bg-[#e7f6ef] px-3 py-1 text-xs font-medium text-success ring-1 ring-inset ring-[#c4ebdc]"
                    >
                      <CircleCheck className="h-3.5 w-3.5" aria-hidden />
                      {topic}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Needs work" />
            <CardContent>
              {weakTopics.length === 0 ? (
                <p className="text-sm text-ink-2">
                  No weak topics yet — keep practicing.
                </p>
              ) : (
                <ul className="flex flex-wrap gap-2">
                  {weakTopics.map((topic) => (
                    <li
                      key={topic}
                      className="inline-flex items-center gap-1.5 rounded-full bg-[#fdf3e2] px-3 py-1 text-xs font-medium text-[#b57a09] ring-1 ring-inset ring-[#f5dfb4]"
                    >
                      <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
                      {topic}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Get set up" />
            <CardContent className="space-y-3">
              {ONBOARDING_STEPS.map((step, index) => (
                <Link
                  key={step.title}
                  href={step.href}
                  className="group flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5 transition-colors hover:border-brand hover:bg-brand-50"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand transition-colors group-hover:bg-brand group-hover:text-white">
                    {index + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-ink">
                      {step.title}
                    </span>
                    <span className="mt-0.5 block text-[13px] leading-snug text-ink-2">
                      {step.text}
                    </span>
                  </span>
                </Link>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
