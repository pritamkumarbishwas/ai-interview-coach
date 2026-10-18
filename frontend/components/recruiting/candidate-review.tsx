"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Columns3, Film, Play } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { toApiError } from "@/lib/api";
import {
  INTEGRITY_LEVEL_LABELS,
  INTEGRITY_LEVEL_TONES,
} from "@/lib/recruiting";
import { cx } from "@/lib/utils";
import * as invitationService from "@/services/invitations";
import type {
  IntegrityReport,
  ReviewTimeline,
  Scorecard,
  ShortlistEntry,
  TimelineEntry,
} from "@/types";

/** m:ss elapsed label for a recording offset. */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const mins = Math.floor(whole / 60);
  return `${mins}:${String(whole % 60).padStart(2, "0")}`;
}

interface CandidateTimelineModalProps {
  invitationId: string | null;
  candidateName: string;
  open: boolean;
  onClose: () => void;
}

/**
 * Reviewer timeline: the candidate's answers and advisory integrity moments
 * interleaved by recording offset. Clicking an entry seeks the recording.
 */
export function CandidateTimelineModal({
  invitationId,
  candidateName,
  open,
  onClose,
}: CandidateTimelineModalProps) {
  const [timeline, setTimeline] = useState<ReviewTimeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!open || !invitationId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setVideoError(null);
    setTimeline(null);

    invitationService
      .getInvitationTimeline(invitationId)
      .then(async (loaded) => {
        if (cancelled) return;
        setTimeline(loaded);
        if (!loaded.recording_available) return;
        try {
          const blob = await invitationService.getInvitationRecordingBlob(
            invitationId,
          );
          if (!cancelled) setVideoUrl(URL.createObjectURL(blob));
        } catch (caught) {
          if (!cancelled) setVideoError(toApiError(caught).message);
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(toApiError(caught).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, invitationId]);

  // Revoke the object URL whenever it changes or the modal unmounts.
  useEffect(() => {
    if (!videoUrl) return;
    return () => URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  const seek = useCallback((seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    void video.play().catch(() => {
      /* autoplay may be blocked; the user can press play */
    });
  }, []);

  const entries = timeline?.entries ?? [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Session timeline"
      description={`${candidateName} — advisory navigation over the recording.`}
      className="max-w-3xl!"
    >
      {loading ? (
        <p className="text-sm text-ink-2">Loading timeline…</p>
      ) : error ? (
        <Alert tone="error">{error}</Alert>
      ) : timeline ? (
        <div className="space-y-4">
          {timeline.recording_available ? (
            <div className="space-y-2">
              {videoUrl ? (
                <video
                  ref={videoRef}
                  src={videoUrl}
                  controls
                  className="max-h-[380px] w-full rounded-btn bg-black"
                />
              ) : videoError ? (
                <Alert tone="error">{videoError}</Alert>
              ) : (
                <p className="text-sm text-ink-2">Loading recording…</p>
              )}
              {!timeline.anchored_to_recording ? (
                <p className="text-xs text-ink-3">
                  Offsets are approximate — this session did not report an exact
                  capture start.
                </p>
              ) : null}
            </div>
          ) : (
            <p className="flex items-center gap-2 text-sm text-ink-2">
              <Film className="h-4 w-4" aria-hidden />
              No recording is available for this session; the transcript order is
              still listed below.
            </p>
          )}

          {entries.length === 0 ? (
            <p className="text-[13px] text-ink-2">Nothing captured yet.</p>
          ) : (
            <ol className="space-y-2">
              {entries.map((entry, index) => (
                <TimelineRow
                  key={`${entry.kind}-${index}`}
                  entry={entry}
                  seekable={Boolean(videoUrl)}
                  onSeek={seek}
                />
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </Modal>
  );
}

function TimelineRow({
  entry,
  seekable,
  onSeek,
}: {
  entry: TimelineEntry;
  seekable: boolean;
  onSeek: (seconds: number) => void;
}) {
  if (entry.kind === "signal") {
    return (
      <li className="rounded-btn border border-line bg-surface px-3 py-2">
        <div className="flex items-center gap-2">
          <Badge tone="warning">Signal</Badge>
          <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
            {entry.label}
          </span>
          <span className="tabular-nums text-xs text-ink-2">
            {clock(entry.at_seconds)}
          </span>
        </div>
      </li>
    );
  }

  return (
    <li className="rounded-btn border border-line px-3 py-2.5">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-ink">
            {entry.question || "Question"}
          </p>
          {entry.answer ? (
            <p className="mt-1 line-clamp-3 text-xs text-ink-2">{entry.answer}</p>
          ) : null}
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            {entry.competency ? <span>{entry.competency}</span> : null}
            {entry.score !== null ? (
              <span className="tabular-nums">{entry.score}/100</span>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="tabular-nums text-xs text-ink-2">
            {clock(entry.at_seconds)}
          </span>
          {seekable ? (
            <button
              type="button"
              onClick={() => onSeek(entry.at_seconds)}
              className="inline-flex items-center gap-1 rounded-btn px-1.5 py-0.5 text-xs font-medium text-brand transition-colors hover:bg-mist"
            >
              <Play className="h-3 w-3" aria-hidden />
              Jump
            </button>
          ) : null}
        </div>
      </div>
    </li>
  );
}

interface CompareModalProps {
  entries: ShortlistEntry[];
  open: boolean;
  onClose: () => void;
}

/** Side-by-side comparison of two candidates' advisory scorecards. */
export function CompareModal({ entries, open, onClose }: CompareModalProps) {
  const completed = useMemo(
    () => entries.filter((entry) => entry.status === "completed"),
    [entries],
  );
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [left, setLeft] = useState<Scorecard | null>(null);
  const [right, setRight] = useState<Scorecard | null>(null);
  const [leftIntegrity, setLeftIntegrity] = useState<IntegrityReport | null>(null);
  const [rightIntegrity, setRightIntegrity] = useState<IntegrityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!leftId && completed[0]) setLeftId(completed[0].invitation_id);
    if (!rightId && completed[1]) setRightId(completed[1].invitation_id);
  }, [open, completed, leftId, rightId]);

  useEffect(() => {
    if (!open || !leftId || !rightId || leftId === rightId) {
      setLeft(null);
      setRight(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      invitationService.getInvitationScorecard(leftId),
      invitationService.getInvitationScorecard(rightId),
      invitationService.getInvitationIntegrity(leftId).catch(() => null),
      invitationService.getInvitationIntegrity(rightId).catch(() => null),
    ])
      .then(([leftCard, rightCard, leftReport, rightReport]) => {
        if (cancelled) return;
        setLeft(leftCard);
        setRight(rightCard);
        setLeftIntegrity(leftReport);
        setRightIntegrity(rightReport);
      })
      .catch((caught) => {
        if (!cancelled) setError(toApiError(caught).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, leftId, rightId]);

  const competencies = useMemo(() => {
    const names = new Set<string>();
    left?.competencies.forEach((item) => names.add(item.competency));
    right?.competencies.forEach((item) => names.add(item.competency));
    return [...names];
  }, [left, right]);

  const scoreOf = (card: Scorecard | null, name: string) =>
    card?.competencies.find((item) => item.competency === name)?.score ?? null;

  const leftEntry = completed.find((entry) => entry.invitation_id === leftId);
  const rightEntry = completed.find((entry) => entry.invitation_id === rightId);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Compare candidates"
      description="Advisory scores, side by side — a human always decides."
      className="max-w-3xl!"
    >
      {completed.length < 2 ? (
        <p className="text-sm text-ink-2">
          Two completed interviews are needed to compare candidates.
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <CandidatePicker
              label="Candidate A"
              value={leftId}
              options={completed}
              onChange={setLeftId}
            />
            <CandidatePicker
              label="Candidate B"
              value={rightId}
              options={completed}
              onChange={setRightId}
            />
          </div>

          {leftId && rightId && leftId === rightId ? (
            <Alert tone="info">Pick two different candidates.</Alert>
          ) : error ? (
            <Alert tone="error">{error}</Alert>
          ) : loading ? (
            <p className="text-sm text-ink-2">Loading scorecards…</p>
          ) : left && right ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <CandidateHeadline
                  name={leftEntry ? displayName(leftEntry) : "Candidate A"}
                  entry={leftEntry}
                  card={left}
                  integrity={leftIntegrity}
                />
                <CandidateHeadline
                  name={rightEntry ? displayName(rightEntry) : "Candidate B"}
                  entry={rightEntry}
                  card={right}
                  integrity={rightIntegrity}
                />
              </div>

              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-xs text-ink-3">
                    <th className="pb-1.5 font-medium">Competency</th>
                    <th className="pb-1.5 text-right font-medium">A</th>
                    <th className="pb-1.5 text-right font-medium">B</th>
                  </tr>
                </thead>
                <tbody>
                  {competencies.map((name) => {
                    const a = scoreOf(left, name);
                    const b = scoreOf(right, name);
                    return (
                      <tr key={name} className="border-t border-line">
                        <td className="py-1.5 text-ink">{name}</td>
                        <td
                          className={cx(
                            "py-1.5 text-right tabular-nums",
                            a !== null && b !== null && a > b ? "font-semibold text-ink" : "text-ink-2",
                          )}
                        >
                          {a ?? "—"}
                        </td>
                        <td
                          className={cx(
                            "py-1.5 text-right tabular-nums",
                            a !== null && b !== null && b > a ? "font-semibold text-ink" : "text-ink-2",
                          )}
                        >
                          {b ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                  <tr className="border-t border-line">
                    <td className="py-1.5 font-medium text-ink">Overall</td>
                    <td className="py-1.5 text-right font-semibold tabular-nums text-ink">
                      {left.overall_score}
                    </td>
                    <td className="py-1.5 text-right font-semibold tabular-nums text-ink">
                      {right.overall_score}
                    </td>
                  </tr>
                </tbody>
              </table>

              <div className="grid gap-3 sm:grid-cols-2">
                <CandidateNotes card={left} />
                <CandidateNotes card={right} />
              </div>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}

function CandidatePicker({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: ShortlistEntry[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-2">{label}</span>
      <select
        className="h-9 w-full rounded-btn border border-line bg-card px-2 text-[13px] text-ink"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((entry) => (
          <option key={entry.invitation_id} value={entry.invitation_id}>
            {entry.candidate_name || entry.candidate_email}
          </option>
        ))}
      </select>
    </label>
  );
}

function CandidateHeadline({
  name,
  entry,
  card,
  integrity,
}: {
  name: string;
  entry: ShortlistEntry | undefined;
  card: Scorecard;
  integrity: IntegrityReport | null;
}) {
  return (
    <div className="rounded-btn border border-line px-3 py-2.5">
      <p className="truncate text-[13px] font-medium text-ink">{name}</p>
      <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-2">
        <span className="tabular-nums">
          {card.overall_score}/100
          {card.threshold > 0 ? ` · threshold ${card.threshold}` : ""}
        </span>
        {entry?.percentile !== null && entry?.percentile !== undefined ? (
          <span className="tabular-nums">{entry.percentile}th pct</span>
        ) : null}
        <Badge tone={card.meets_threshold ? "success" : "muted"}>
          {card.meets_threshold ? "Meets threshold" : "Below threshold"}
        </Badge>
        {integrity ? (
          <Badge tone={INTEGRITY_LEVEL_TONES[integrity.level]}>
            {INTEGRITY_LEVEL_LABELS[integrity.level]}
          </Badge>
        ) : null}
      </p>
      <p className="mt-1 truncate text-xs text-ink-3">{card.role}</p>
    </div>
  );
}

function displayName(entry: ShortlistEntry): string {
  return entry.candidate_name || entry.candidate_email;
}

function CandidateNotes({ card }: { card: Scorecard }) {
  if (card.strengths.length === 0 && card.concerns.length === 0) {
    return <div />;
  }
  return (
    <div className="text-xs text-ink-3">
      {card.strengths.length > 0 ? (
        <p>Strengths: {card.strengths.join(", ")}.</p>
      ) : null}
      {card.concerns.length > 0 ? <p>Concerns: {card.concerns.join(", ")}.</p> : null}
    </div>
  );
}

/** Trigger button + modal for the compare workspace (holds its own state). */
export function CompareCandidatesButton({
  entries,
}: {
  entries: ShortlistEntry[];
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        icon={<Columns3 className="h-3.5 w-3.5" aria-hidden />}
        onClick={() => setOpen(true)}
      >
        Compare
      </Button>
      <CompareModal entries={entries} open={open} onClose={() => setOpen(false)} />
    </>
  );
}
