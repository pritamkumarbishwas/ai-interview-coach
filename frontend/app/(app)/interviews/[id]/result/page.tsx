"use client";

import Link from "next/link";

import {
  ArrowLeft,
  ArrowRight,
  Award,
  CircleCheck,
  ClipboardList,
  Lightbulb,
  Mic,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { MOCK_REPORT } from "@/data/mock";

export default function ResultPage() {
  const report = MOCK_REPORT;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href="/interviews"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 transition-colors hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to interviews
      </Link>

      <section className="overflow-hidden rounded-card border border-line bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04)]">
        <div className="flex flex-col items-center gap-5 bg-gradient-to-b from-brand-50 to-card px-6 py-8 text-center sm:px-8">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand text-white shadow-md">
            <Award className="h-7 w-7" aria-hidden />
          </span>
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-ink">
              Interview Complete
            </h2>
            <p className="mt-1 text-sm text-ink-2">
              {report.role} · {report.type} · {report.date} · {report.duration}
            </p>
          </div>
          <div className="flex items-end gap-2">
            <span className="text-6xl font-bold leading-none tracking-tight text-ink tabular-nums">
              {report.overall}
            </span>
            <span className="pb-1.5 text-xl font-semibold text-ink-3">/100</span>
          </div>
          <Badge tone="brand">{report.label}</Badge>
        </div>
      </section>

      <section
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Performance breakdown"
      >
        {report.performance.map((metric) => (
          <StatCard
            key={metric.label}
            label={metric.label}
            value={`${metric.value}%`}
            icon={
              metric.label.includes("Technical") ? (
                <Target className="h-4 w-4" />
              ) : metric.label.includes("Communication") ? (
                <Sparkles className="h-4 w-4" />
              ) : metric.label.includes("Problem") ? (
                <TrendingUp className="h-4 w-4" />
              ) : (
                <ClipboardList className="h-4 w-4" />
              )
            }
          />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <CardHeader
            title="Strong Areas"
            description="Dimensions you scored well on."
          />
          <CardContent className="flex flex-wrap gap-2">
            {report.strongAreas.map((area) => (
              <span
                key={area}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#bfe8d5] bg-[#e7f6ef] px-3 py-1.5 text-[13px] font-medium text-[#18794e]"
              >
                <CircleCheck className="h-3.5 w-3.5" aria-hidden />
                {area}
              </span>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Needs Improvement"
            description="Focus areas for your next session."
          />
          <CardContent className="flex flex-wrap gap-2">
            {report.needsImprovement.map((area) => (
              <span
                key={area}
                className="inline-flex items-center gap-1.5 rounded-full border border-[#f3d3a8] bg-brand-50 px-3 py-1.5 text-[13px] font-medium text-brand-hover"
              >
                <Target className="h-3.5 w-3.5" aria-hidden />
                {area}
              </span>
            ))}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader
          title="AI Recommendations"
          description="Three concrete steps to raise your score."
        />
        <CardContent className="space-y-3">
          {report.recommendations.map((item, index) => (
            <div
              key={item}
              className="flex items-start gap-3 rounded-xl border border-line bg-surface p-4"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand">
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{item}</p>
                <p className="mt-0.5 text-[13px] text-ink-2">
                  {index === 0
                    ? "Practice designing a URL shortener or chat system end to end."
                    : index === 1
                      ? "Review B-tree vs hash indexes and when each helps."
                      : "Use the STAR structure and close each story with a metric."
                  }
                </p>
              </div>
              <Lightbulb
                className="ml-auto mt-1 h-4 w-4 shrink-0 text-brand"
                aria-hidden
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <section className="flex flex-wrap items-center justify-center gap-3 pb-4">
        <ButtonLink
          href="/practice"
          size="lg"
          icon={<Mic className="h-4 w-4" />}
        >
          Start Another Interview
        </ButtonLink>
        <ButtonLink href="/results" variant="outline" size="lg">
          View Detailed Report
          <ArrowRight className="h-4 w-4" aria-hidden />
        </ButtonLink>
      </section>
    </div>
  );
}
