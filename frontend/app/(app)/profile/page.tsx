"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  Award,
  BookOpen,
  Clock,
  Mail,
  Save,
  Target,
  Trophy,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { StatCard } from "@/components/ui/stat-card";
import { MOCK_STATS } from "@/data/mock";
import { useAuth } from "@/hooks/use-auth";
import { toApiError } from "@/lib/api";
import { formatDate } from "@/lib/utils";

const SKILLS = [
  "React",
  "TypeScript",
  "Node.js",
  "REST APIs",
  "PostgreSQL",
  "System Design",
];

const PREFERENCES = [
  {
    id: "reminders",
    label: "Daily practice reminders",
    detail: "A gentle nudge at 6:00 PM to keep your streak going.",
    enabled: true,
  },
  {
    id: "followups",
    label: "AI follow-up questions",
    detail: "The interviewer asks deeper questions on weak answers.",
    enabled: true,
  },
  {
    id: "transcript",
    label: "Save full transcripts",
    detail: "Store every conversation for later review.",
    enabled: false,
  },
];

export default function ProfilePage() {
  const { user, updateProfile } = useAuth();
  const name = user?.name ?? "";
  const email = user?.email ?? "";
  const memberSince = user?.created_at ? formatDate(user.created_at) : "";

  const [displayName, setDisplayName] = useState(name);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preferences, setPreferences] = useState(
    Object.fromEntries(PREFERENCES.map((item) => [item.id, item.enabled])),
  );

  useEffect(() => {
    setDisplayName(name);
  }, [name]);

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 2000);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const nextName = displayName.trim();
    if (!nextName || saving) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateProfile({ name: nextName });
      setSaved(true);
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-bold tracking-tight text-ink">Profile</h2>
        <p className="mt-1.5 text-sm text-ink-2">
          Manage your account, skills, and practice preferences.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Account" />
            <CardContent>
              <form onSubmit={onSubmit} className="space-y-4" noValidate>
                <div className="flex items-center gap-4">
                  <Avatar name={name} size="lg" />
                  <div>
                    <p className="text-base font-semibold text-ink">{name}</p>
                    <p className="flex items-center gap-1.5 text-[13px] text-ink-2">
                      <Mail className="h-3.5 w-3.5" aria-hidden />
                      {email}
                    </p>
                  </div>
                </div>

                {error ? <Alert tone="error">{error}</Alert> : null}

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Full name" htmlFor="name" required>
                    <Input
                      id="name"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                    />
                  </Field>
                  <Field label="Email" htmlFor="email" hint="Read-only">
                    <Input id="email" type="email" value={email} disabled />
                  </Field>
                  <Field
                    label="Member since"
                    htmlFor="since"
                    hint="Read-only"
                  >
                    <Input id="since" value={memberSince} disabled />
                  </Field>
                </div>

                <div className="flex items-center gap-3 pt-1">
                  <Button
                    type="submit"
                    loading={saving}
                    icon={<Save className="h-4 w-4" />}
                  >
                    Save changes
                  </Button>
                  {saved ? (
                    <span className="text-[13px] font-medium text-success">
                      Changes saved
                    </span>
                  ) : null}
                </div>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Practice preferences"
              description="Tune how the AI interviewer behaves."
            />
            <CardContent className="divide-y divide-line">
              {PREFERENCES.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between gap-4 py-3.5 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">{item.label}</p>
                    <p className="mt-0.5 text-[13px] text-ink-2">
                      {item.detail}
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={preferences[item.id]}
                    aria-label={item.label}
                    onClick={() =>
                      setPreferences((prev) => ({
                        ...prev,
                        [item.id]: !prev[item.id],
                      }))
                    }
                    className={
                      preferences[item.id]
                        ? "relative h-6 w-11 shrink-0 rounded-full bg-brand transition-colors"
                        : "relative h-6 w-11 shrink-0 rounded-full bg-line transition-colors"
                    }
                  >
                    <span
                      className={
                        preferences[item.id]
                          ? "absolute left-5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
                          : "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform"
                      }
                    />
                  </button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Your skills" description="Used to tailor questions." />
            <CardContent className="flex flex-wrap gap-2">
              {SKILLS.map((skill) => (
                <span
                  key={skill}
                  className="rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink-2"
                >
                  {skill}
                </span>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Progress" />
            <CardContent className="space-y-4">
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand">
                  <Trophy className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">Top 15%</p>
                  <p className="text-[13px] text-ink-2">
                    of learners this month
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand">
                  <Award className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">3-day streak</p>
                  <p className="text-[13px] text-ink-2">
                    Practice today to keep it alive
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand">
                  <Target className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">
                    Goal: 5 interviews
                  </p>
                  <p className="text-[13px] text-ink-2">3 completed this week</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4">
            <StatCard
              label="Interviews"
              value={MOCK_STATS.totalInterviews}
              icon={<BookOpen className="h-4 w-4" />}
            />
            <StatCard
              label="Practice time"
              value={MOCK_STATS.practiceTime}
              icon={<Clock className="h-4 w-4" />}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
