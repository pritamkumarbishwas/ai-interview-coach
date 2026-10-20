"use client";

import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";

import { FileText, FileUp, Trash, Upload } from "lucide-react";

import { ResumeDetailDialog } from "@/components/resumes/resume-detail-dialog";
import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonList } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import * as resumeService from "@/services/resumes";
import { formatBytes, formatDate } from "@/lib/utils";
import type { ResumeAnalysisStatus, ResumeSummary } from "@/types";

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];
const MAX_SIZE = 5 * 1024 * 1024;

const STATUS_META: Record<
  ResumeAnalysisStatus,
  { label: string; tone: BadgeTone }
> = {
  pending: { label: "Queued", tone: "brand" },
  processing: { label: "Analysing", tone: "ai" },
  ready: { label: "Ready", tone: "success" },
  partial: { label: "Partially ready", tone: "warning" },
  failed: { label: "Analysis failed", tone: "danger" },
  deleting: { label: "Deleting", tone: "muted" },
};

export default function ResumesPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [openResumeId, setOpenResumeId] = useState<string | null>(null);

  const {
    data: resumes,
    loading,
    error: listError,
    reload,
  } = useAsync(() => resumeService.listResumes(), []);

  const items = resumes ?? [];
  const hasProcessing = items.some((resume) =>
    resumeService.isResumeProcessing(resume.analysis_status),
  );

  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(reload, resumeService.RESUME_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasProcessing, reload]);

  const pickFile = (file: File | null | undefined) => {
    setError(null);
    setSuccess(null);
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    const typeOk =
      ACCEPTED_TYPES.includes(file.type) ||
      ["pdf", "docx"].includes(extension ?? "");
    if (!typeOk) {
      setSelected(null);
      setError("Only PDF and DOCX files are supported.");
      return;
    }
    if (file.size > MAX_SIZE) {
      setSelected(null);
      setError("File is too large. The maximum size is 5 MB.");
      return;
    }
    setSelected(file);
  };

  const onInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    pickFile(event.target.files?.[0]);
    event.target.value = "";
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    pickFile(event.dataTransfer.files?.[0]);
  };

  const onUpload = async () => {
    if (!selected || uploading) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const created = await resumeService.uploadResume(selected);
      if (created.deduplicated) {
        setSuccess(`"${created.filename}" is already in your library.`);
      } else if (created.analysis_status === "failed") {
        setSuccess(
          `"${created.filename}" was saved. AI analysis failed, but you can retry it from the resume card.`,
        );
      } else if (resumeService.isResumeProcessing(created.analysis_status)) {
        setSuccess(`"${created.filename}" was uploaded and is being analysed.`);
      } else {
        setSuccess(`"${created.filename}" was uploaded and processed.`);
      }
      setSelected(null);
      reload();
      if (created.deduplicated || !resumeService.isResumeProcessing(created.analysis_status)) {
        setOpenResumeId(created.id);
      }
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setUploading(false);
    }
  };

  const removeResume = async (id: string) => {
    setDeletingId(id);
    setError(null);
    try {
      await resumeService.deleteResume(id);
      reload();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setDeletingId(null);
    }
  };

  const showListSkeleton = loading && resumes === null;

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-2xl font-bold tracking-tight text-ink">Resumes</h2>
        <p className="mt-1.5 text-sm text-ink-2">
          Ground interview questions in your real experience. Snapshots, text and
          the original file are kept together.
        </p>
      </section>

      <Card>
        <CardHeader
          title="Upload a resume"
          description="PDF or DOCX, up to 5 MB. We keep the original, extract every section, render page previews and read scanned pages with OCR."
        />
        <CardContent className="space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          {success ? <Alert tone="success">{success}</Alert> : null}

          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragging
                ? "border-brand bg-brand-50"
                : "border-line bg-surface hover:border-brand-border"
            }`}
          >
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-card text-brand shadow-sm">
              <FileUp className="h-5 w-5" aria-hidden />
            </span>
            <p className="mt-3 text-sm font-medium text-ink">
              Drag and drop your resume here
            </p>
            <p className="mt-1 text-sm text-ink-2">or</p>
            <div className="mt-3">
              <Button
                variant="outline"
                onClick={() => inputRef.current?.click()}
                icon={<Upload className="h-4 w-4" aria-hidden />}
              >
                Browse files
              </Button>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={onInputChange}
              aria-label="Choose resume file"
            />
          </div>

          {selected ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-surface px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <FileText className="h-5 w-5 shrink-0 text-brand" aria-hidden />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    {selected.name}
                  </p>
                  <p className="text-xs text-ink-2">
                    {formatBytes(selected.size)}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelected(null)}
                  disabled={uploading}
                >
                  Remove
                </Button>
                <Button
                  size="sm"
                  onClick={onUpload}
                  loading={uploading}
                  icon={<Upload className="h-4 w-4" aria-hidden />}
                >
                  {uploading ? "Uploading..." : "Upload resume"}
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <section aria-label="Your resumes" className="space-y-3">
        <h2 className="text-sm font-semibold text-ink">
          Your resumes{" "}
          <span className="font-normal text-ink-3">({items.length})</span>
        </h2>

        {listError ? (
          <Alert tone="error">
            {listError.message}{" "}
            <button type="button" onClick={reload} className="font-medium underline">
              Retry
            </button>
          </Alert>
        ) : showListSkeleton ? (
          <SkeletonList rows={3} />
        ) : items.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {items.map((resume) => (
              <ResumeCard
                key={resume.id}
                resume={resume}
                busy={deletingId === resume.id}
                onView={() => setOpenResumeId(resume.id)}
                onRemove={() => void removeResume(resume.id)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title="No resumes yet"
            description="Upload your first resume to ground interview questions in your real experience."
          />
        )}
      </section>

      <ResumeDetailDialog
        resumeId={openResumeId}
        onClose={() => setOpenResumeId(null)}
        onDeleted={reload}
      />
    </div>
  );
}

function ResumeCard({
  resume,
  busy,
  onView,
  onRemove,
}: {
  resume: ResumeSummary;
  busy: boolean;
  onView: () => void;
  onRemove: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const extension =
    resume.filename.split(".").pop()?.toUpperCase() ?? "FILE";
  const skills = resume.skills.slice(0, 3);
  const remaining = resume.skills.length - skills.length;
  const meta = STATUS_META[resume.analysis_status];
  const processing = resumeService.isResumeProcessing(resume.analysis_status);

  return (
    <Card>
      <CardContent className="flex items-start gap-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
          <FileText className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onView}
            className="block max-w-full truncate text-left text-sm font-medium text-ink hover:underline"
          >
            {resume.filename}
          </button>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <Badge tone={meta.tone}>
              {processing ? (
                <span className="mr-1 h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              ) : null}
              {meta.label}
            </Badge>
            <Badge tone="brand">{extension}</Badge>
            {resume.page_count > 0 ? (
              <span className="text-xs text-ink-2">
                {resume.page_count} page{resume.page_count === 1 ? "" : "s"}
              </span>
            ) : null}
            {resume.ocr_used ? (
              <span className="text-xs text-ink-2">OCR</span>
            ) : null}
            {resume.file_size > 0 ? (
              <span className="text-xs text-ink-2">
                {formatBytes(resume.file_size)}
              </span>
            ) : null}
            <span className="text-xs text-ink-3">
              Added {formatDate(resume.created_at)}
            </span>
          </div>
          {skills.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <Badge key={skill} tone="neutral">
                  {skill}
                </Badge>
              ))}
              {remaining > 0 ? (
                <span className="text-xs text-ink-3">+{remaining} more</span>
              ) : null}
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={onView}>
              View details
            </Button>
            {confirming ? (
              <>
                <span className="text-xs font-medium text-danger-ink">
                  Delete permanently?
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={onRemove}
                  loading={busy}
                >
                  Delete
                </Button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                disabled={busy}
                aria-label={`Delete ${resume.filename}`}
                className="rounded-btn p-2 text-ink-3 transition-colors hover:bg-danger-soft hover:text-danger-ink disabled:opacity-50"
              >
                <Trash className="h-4 w-4" aria-hidden />
              </button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
