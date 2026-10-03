"use client";

import Link from "next/link";

import {
  ArrowRight,
  ChevronRight,
  Clock,
  Mic,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import {
  MOCK_INTERVIEWS,
  MOCK_STATS,
  type InterviewTypeLabel,
} from "@/data/mock";
import { useAuth } from "@/hooks/use-auth";
import { cx, greeting } from "@/lib/utils";

const TYPE_TONES: Record<InterviewTypeLabel, BadgeTone> = {
  Technical: "ai",
  Behavioral: "success",
  HR: "neutral",
  Mixed: "warning",
  "System Design": "brand",
};

const ONBOARDING_STEPS = [
  {
    title: "Upload your resume",
    text: "PDF or DOCX — we extract your skills and experience.",
    href: "/practice",
  },
  {
    title: "Add a job description",
    text: "Paste the role you are targeting so questions match it.",
    href: "/practice",
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
  const recent = MOCK_INTERVIEWS.slice(0, 4);

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
          <ButtonLink href="/results" variant="outline">
            View Reports
          </ButtonLink>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Overview statistics">
        <StatCard
          label="Total Interviews"
          value={MOCK_STATS.totalInterviews}
          icon={<Target className="h-4 w-4" />}
          trend={{ value: "+3 this week", direction: "up" }}
        />
        <StatCard
          label="Average Score"
          value={`${MOCK_STATS.averageScore}%`}
          icon={<TrendingUp className="h-4 w-4" />}
          trend={{ value: "+4% vs last week", direction: "up" }}
        />
        <StatCard
          label="Questions Answered"
          value={MOCK_STATS.questionsAnswered}
          icon={<Sparkles className="h-4 w-4" />}
        />
        <StatCard
          label="Practice Time"
          value={MOCK_STATS.practiceTime}
          icon={<Clock className="h-4 w-4" />}
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
                        <span className="font-medium text-ink">{item.role}</span>
                      </td>
                      <td className="px-4 py-3.5">
                        <Badge tone={TYPE_TONES[item.type]}>{item.type}</Badge>
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
                      <td className="px-4 py-3.5 text-ink-2">{item.date}</td>
                      <td className="px-4 py-3.5">
                        <Badge tone={item.status === "completed" ? "success" : "brand"}>
                          {item.status === "completed" ? "Completed" : "In progress"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3.5 text-right">
                        <Link
                          href={`/interviews/${item.id}`}
                          className="inline-flex items-center gap-1 rounded-btn px-2 py-1 text-xs font-medium text-brand transition-colors hover:bg-brand-50"
                        >
                          {item.status === "completed" ? "Report" : "Resume"}
                          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
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

          <Card className="overflow-hidden">
            <div className="border-b border-line bg-gradient-to-r from-brand-50 to-brand-100 px-5 py-4">
              <p className="text-sm font-semibold text-brand-hover">
                Weekly goal
              </p>
              <p className={cx("mt-0.5 text-2xl font-bold text-ink")}>
                3 <span className="text-sm font-medium text-ink-2">of 5 interviews</span>
              </p>
            </div>
            <CardContent className="px-5 py-4">
              <div className="h-2 overflow-hidden rounded-full bg-mist">
                <div
                  className="h-full rounded-full bg-brand transition-[width] duration-700"
                  style={{ width: "60%" }}
                />
              </div>
              <p className="mt-2.5 text-[13px] text-ink-2">
                Two more interviews to hit your goal this week.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
