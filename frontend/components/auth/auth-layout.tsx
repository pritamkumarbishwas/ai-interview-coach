import type { ReactNode } from "react";

import { Check, Sparkles, Target } from "lucide-react";

import { Logo } from "@/components/layout/logo";

const HIGHLIGHTS = [
  {
    icon: Target,
    title: "Interviews tailored to your target role",
    text: "Questions are generated from your resume and the job description you are applying for.",
  },
  {
    icon: Sparkles,
    title: "Instant AI feedback on every answer",
    text: "Scores for relevance, technical accuracy, completeness, clarity, and structure.",
  },
  {
    icon: Check,
    title: "A concrete preparation plan",
    text: "Finish with strong topics, weak topics, and what to study next.",
  },
];

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen bg-white">
      <div className="flex w-full flex-col justify-center px-6 py-12 sm:px-12 lg:w-[46%] lg:px-16">
        <div className="mx-auto w-full max-w-md">
          <Logo className="mb-10" />

          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {title}
          </h1>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-2">
            {subtitle}
          </p>

          <div className="mt-8">{children}</div>

          <div className="mt-8 text-sm text-ink-2">{footer}</div>
        </div>
      </div>

      <div className="relative hidden flex-1 overflow-hidden bg-ink lg:block">
        <div
          className="absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,rgba(247,147,30,0.5),transparent_55%)]"
          aria-hidden
        />
        <div
          className="absolute inset-0 bg-[radial-gradient(circle_at_20%_85%,rgba(247,147,30,0.2),transparent_50%)]"
          aria-hidden
        />
        <div className="relative flex h-full flex-col justify-between p-12">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-brand">
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            AI-powered mock interviews
          </div>

          <div className="max-w-md space-y-8">
            <h2 className="text-3xl font-semibold leading-snug text-white">
              Walk into your next interview already knowing your weak spots.
            </h2>
            <ul className="space-y-5">
              {HIGHLIGHTS.map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.title} className="flex gap-3.5">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/20 text-brand">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <div>
                      <p className="text-sm font-medium text-white">
                        {item.title}
                      </p>
                      <p className="mt-1 text-sm leading-relaxed text-white/60">
                        {item.text}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <p className="text-xs text-white/50">
            Practice · Evaluate · Improve
          </p>
        </div>
      </div>
    </div>
  );
}
