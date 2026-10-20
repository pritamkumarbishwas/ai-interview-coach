"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  RefreshCw,
  Trash,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/loading";
import { useAsync } from "@/hooks/use-async";
import { toApiError } from "@/lib/api";
import { cx, formatBytes, formatDate } from "@/lib/utils";
import * as resumeService from "@/services/resumes";
import type {
  ResumeAdditionalSection,
  ResumeAnalysisStatus,
  ResumeAward,
  ResumeCertification,
  ResumeContact,
  ResumeEducation,
  ResumeExperience,
  ResumeLanguage,
  ResumePreview,
  ResumeProject,
  ResumePublication,
  ResumeStructuredData,
} from "@/types";

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

type DetailTab = "preview" | "structured" | "text";

interface ResumeDetailDialogProps {
  resumeId: string | null;
  onClose: () => void;
  onDeleted: () => void;
}

export function ResumeDetailDialog({
  resumeId,
  onClose,
  onDeleted,
}: ResumeDetailDialogProps) {
  const [tab, setTab] = useState<DetailTab>("preview");
  const [actionError, setActionError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [fullText, setFullText] = useState<string | null>(null);
  const [textLoading, setTextLoading] = useState(false);

  const {
    data: resume,
    loading,
    error,
    reload,
  } = useAsync(
    () => (resumeId ? resumeService.getResume(resumeId) : Promise.resolve(null)),
    [resumeId],
  );

  useEffect(() => {
    setTab("preview");
    setFullText(null);
    setActionError(null);
    setConfirmingDelete(false);
  }, [resumeId]);

  useEffect(() => {
    if (!resume || !resumeId) return;
    if (!resumeService.isResumeProcessing(resume.analysis.status)) return;
    const timer = window.setTimeout(reload, resumeService.RESUME_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [resume, resumeId, reload]);

  useEffect(() => {
    if (tab !== "text" || !resumeId || fullText !== null) return;
    let active = true;
    setTextLoading(true);
    resumeService
      .getResumeText(resumeId)
      .then((response) => {
        if (active) setFullText(response.text);
      })
      .catch((caught) => {
        if (active) setActionError(toApiError(caught).message);
      })
      .finally(() => {
        if (active) setTextLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tab, resumeId, fullText]);

  const download = async () => {
    if (!resume || downloading) return;
    setDownloading(true);
    setActionError(null);
    try {
      const { blob, filename } = await resumeService.downloadResumeFile(
        resume.id,
        resume.filename,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setActionError(toApiError(caught).message);
    } finally {
      setDownloading(false);
    }
  };

  const retry = async () => {
    if (!resume || retrying) return;
    setRetrying(true);
    setActionError(null);
    try {
      await resumeService.retryResumeAnalysis(resume.id);
      reload();
    } catch (caught) {
      setActionError(toApiError(caught).message);
    } finally {
      setRetrying(false);
    }
  };

  const remove = async () => {
    if (!resume || deleting) return;
    setDeleting(true);
    setActionError(null);
    try {
      await resumeService.deleteResume(resume.id);
      onDeleted();
      onClose();
    } catch (caught) {
      setActionError(toApiError(caught).message);
      setDeleting(false);
    }
  };

  const meta = STATUS_META[resume?.analysis.status ?? "pending"];

  return (
    <Modal
      open={Boolean(resumeId)}
      onClose={onClose}
      title={resume?.filename ?? "Resume details"}
      description={
        resume
          ? `${resume.page_count} page${resume.page_count === 1 ? "" : "s"} - ${formatBytes(
              resume.file_size,
            )} - added ${formatDate(resume.created_at)}`
          : "Loading the stored resume and its extracted content."
      }
      className="max-w-5xl"
    >
      {error ? (
        <Alert tone="error">
          {error.message}{" "}
          <button type="button" onClick={reload} className="font-medium underline">
            Retry
          </button>
        </Alert>
      ) : loading || !resume ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-52" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={meta.tone}>{meta.label}</Badge>
              <Badge tone="neutral">
                {resume.mime_type.includes("pdf") ? "PDF" : "DOCX"}
              </Badge>
              {resume.ocr_pages.length > 0 ? (
                <Badge tone="ai">OCR used</Badge>
              ) : null}
              {resume.analysis.failed_chunks > 0 ? (
                <Badge tone="warning">
                  {resume.analysis.failed_chunks} section
                  {resume.analysis.failed_chunks === 1 ? "" : "s"} missed
                </Badge>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void download()}
                loading={downloading}
                icon={<Download className="h-4 w-4" aria-hidden />}
              >
                Download
              </Button>
              {resume.analysis.status === "failed" ||
              resume.analysis.status === "partial" ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void retry()}
                  loading={retrying}
                  icon={<RefreshCw className="h-4 w-4" aria-hidden />}
                >
                  Retry analysis
                </Button>
              ) : null}
              {confirmingDelete ? (
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmingDelete(false)}
                    disabled={deleting}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => void remove()}
                    loading={deleting}
                  >
                    Delete permanently
                  </Button>
                </div>
              ) : (
                <Button
                  variant="danger-soft"
                  size="sm"
                  onClick={() => setConfirmingDelete(true)}
                  icon={<Trash className="h-4 w-4" aria-hidden />}
                >
                  Delete
                </Button>
              )}
            </div>
          </div>

          {actionError ? <Alert tone="error">{actionError}</Alert> : null}

          {resume.analysis.status === "failed" ? (
            <Alert tone="error">
              {resume.analysis.error_message ||
                "AI analysis failed. The original file and extracted text are still stored."}
            </Alert>
          ) : null}
          {resume.analysis.status === "partial" ? (
            <Alert tone="warning">
              {resume.analysis.warnings[0] ??
                "Some content could not be analysed, but the stored resume is usable."}
            </Alert>
          ) : null}
          {resumeService.isResumeProcessing(resume.analysis.status) ? (
            <Alert tone="info">
              We are extracting every section, rendering page previews and
              analysing the resume. This panel updates automatically.
            </Alert>
          ) : null}

          <div
            role="tablist"
            aria-label="Resume content"
            className="flex flex-wrap gap-1 rounded-xl bg-mist p-1"
          >
            {(
              [
                ["preview", "Page previews", ImageIcon],
                ["structured", "Structured content", FileText],
                ["text", "Full text", FileText],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => setTab(value)}
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors",
                  tab === value
                    ? "bg-card text-ink shadow-sm"
                    : "text-ink-2 hover:text-ink",
                )}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {label}
              </button>
            ))}
          </div>

          {tab === "preview" ? (
            <PreviewGrid resumeId={resume.id} previews={resume.previews} />
          ) : null}
          {tab === "structured" ? (
            <StructuredContent data={resume.structured_data} />
          ) : null}
          {tab === "text" ? (
            textLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-card border border-line bg-surface p-4 text-[13px] leading-relaxed text-ink-2">
                {fullText || resume.raw_text || "No text was extracted."}
              </pre>
            )
          ) : null}
        </div>
      )}
    </Modal>
  );
}

function PreviewGrid({
  resumeId,
  previews,
}: {
  resumeId: string;
  previews: ResumePreview[];
}) {
  const pages = useMemo(
    () => [...previews].sort((a, b) => a.page - b.page),
    [previews],
  );
  if (pages.length === 0) {
    return (
      <p className="rounded-card border border-line bg-surface p-6 text-sm text-ink-2">
        No page previews are available for this document.
      </p>
    );
  }
  return (
    <div className="max-h-[60vh] overflow-auto rounded-card border border-line bg-surface p-3">
      <div className="grid gap-4 sm:grid-cols-2">
        {pages.map((preview) => (
          <PreviewImage
            key={preview.page}
            resumeId={resumeId}
            page={preview.page}
          />
        ))}
      </div>
    </div>
  );
}

function PreviewImage({ resumeId, page }: { resumeId: string; page: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    resumeService
      .getResumePreview(resumeId, page)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) {
          setUrl(objectUrl);
        } else {
          URL.revokeObjectURL(objectUrl);
        }
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [resumeId, page]);

  return (
    <figure className="overflow-hidden rounded-card border border-line bg-card">
      <div className="flex min-h-40 items-center justify-center bg-mist">
        {failed ? (
          <p className="p-4 text-xs text-ink-2">Preview unavailable.</p>
        ) : url ? (
          // Blob URLs are generated from authenticated API responses.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={`Resume page ${page}`}
            className="h-auto w-full"
            loading="lazy"
          />
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </div>
      <figcaption className="border-t border-line px-3 py-2 text-xs text-ink-3">
        Page {page}
      </figcaption>
    </figure>
  );
}

function StructuredContent({ data }: { data: ResumeStructuredData }) {
  const hasAnything =
    data.summary ||
    data.skills.length > 0 ||
    data.experience.length > 0 ||
    data.projects.length > 0 ||
    data.education.length > 0 ||
    data.certifications.length > 0 ||
    data.awards.length > 0 ||
    data.publications.length > 0 ||
    data.languages.length > 0 ||
    data.volunteer.length > 0 ||
    data.interests.length > 0 ||
    data.additional_sections.length > 0;

  return (
    <div className="max-h-[60vh] space-y-5 overflow-auto rounded-card border border-line bg-surface p-5">
      <ContactBlock contact={data.contact} />
      {data.summary ? (
        <DetailSection title="Summary">
          <p className="text-sm leading-relaxed text-ink-2">{data.summary}</p>
        </DetailSection>
      ) : null}
      {data.skills.length > 0 ? (
        <DetailSection title="Skills">
          <div className="flex flex-wrap gap-1.5">
            {data.skills.map((skill) => (
              <Badge key={skill} tone="neutral">
                {skill}
              </Badge>
            ))}
          </div>
        </DetailSection>
      ) : null}
      <ExperienceSection title="Experience" items={data.experience} />
      <ProjectSection items={data.projects} />
      <EducationSection items={data.education} />
      <CertificationSection items={data.certifications} />
      <AwardSection items={data.awards} />
      <PublicationSection items={data.publications} />
      <LanguageSection items={data.languages} />
      <ExperienceSection title="Volunteer" items={data.volunteer} />
      {data.interests.length > 0 ? (
        <DetailSection title="Interests">
          <p className="text-sm text-ink-2">{data.interests.join(", ")}</p>
        </DetailSection>
      ) : null}
      <AdditionalSectionList items={data.additional_sections} />
      {!hasAnything ? (
        <p className="py-8 text-center text-sm text-ink-2">
          No structured content is available yet.
        </p>
      ) : null}
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h4 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-ink-3">
        {title}
      </h4>
      {children}
    </section>
  );
}

function ExperienceSection({
  title,
  items,
}: {
  title: string;
  items: ResumeExperience[];
}) {
  if (items.length === 0) return null;
  return (
    <DetailSection title={title}>
      <div className="space-y-4">
        {items.map((item, index) => (
          <div key={index} className="border-l-2 border-brand-border pl-3">
            <p className="text-sm font-semibold text-ink">
              {item.role || "Role"}
              {item.company ? (
                <span className="font-normal text-ink-2"> at {item.company}</span>
              ) : null}
            </p>
            <p className="text-xs text-ink-3">
              {[item.duration || [item.start_date, item.end_date].filter(Boolean).join(" - "), item.location]
                .filter(Boolean)
                .join(" - ")}
            </p>
            {item.description ? (
              <p className="mt-1 text-sm leading-relaxed text-ink-2">
                {item.description}
              </p>
            ) : null}
            <BulletList items={item.achievements} />
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function ProjectSection({ items }: { items: ResumeProject[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Projects">
      <div className="space-y-4">
        {items.map((item, index) => (
          <div key={index} className="border-l-2 border-brand-border pl-3">
            <p className="text-sm font-semibold text-ink">
              {item.name || "Project"}
            </p>
            {item.description ? (
              <p className="mt-1 text-sm leading-relaxed text-ink-2">
                {item.description}
              </p>
            ) : null}
            {item.technologies.length > 0 ? (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {item.technologies.map((technology) => (
                  <Badge key={technology} tone="brand">
                    {technology}
                  </Badge>
                ))}
              </div>
            ) : null}
            <BulletList items={item.achievements} />
            <LinkList links={item.links} />
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function EducationSection({ items }: { items: ResumeEducation[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Education">
      <div className="space-y-3">
        {items.map((item, index) => (
          <div key={index}>
            <p className="text-sm font-semibold text-ink">
              {item.institution || "Institution"}
            </p>
            <p className="text-sm text-ink-2">
              {[item.degree, item.field_of_study].filter(Boolean).join(", ")}
            </p>
            <p className="text-xs text-ink-3">
              {[item.year || [item.start_date, item.end_date].filter(Boolean).join(" - "), item.grade]
                .filter(Boolean)
                .join(" - ")}
            </p>
            <BulletList items={item.details} />
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function CertificationSection({ items }: { items: ResumeCertification[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Certifications">
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index}>
            <p className="text-sm font-medium text-ink">
              {item.name}
              {item.issuer ? (
                <span className="font-normal text-ink-2"> - {item.issuer}</span>
              ) : null}
            </p>
            <p className="text-xs text-ink-3">
              {[item.issue_date, item.credential_id].filter(Boolean).join(" - ")}
            </p>
            <LinkList links={item.url ? [{ label: item.name, url: item.url }] : []} />
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function AwardSection({ items }: { items: ResumeAward[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Awards">
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index}>
            <p className="text-sm font-medium text-ink">{item.title}</p>
            <p className="text-xs text-ink-3">
              {[item.issuer, item.date].filter(Boolean).join(" - ")}
            </p>
            {item.description ? (
              <p className="text-sm text-ink-2">{item.description}</p>
            ) : null}
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function PublicationSection({ items }: { items: ResumePublication[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Publications">
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index}>
            <p className="text-sm font-medium text-ink">{item.title}</p>
            <p className="text-xs text-ink-3">
              {[item.publisher, item.date].filter(Boolean).join(" - ")}
            </p>
            {item.description ? (
              <p className="text-sm text-ink-2">{item.description}</p>
            ) : null}
            <LinkList links={item.url ? [{ label: item.title, url: item.url }] : []} />
          </div>
        ))}
      </div>
    </DetailSection>
  );
}

function LanguageSection({ items }: { items: ResumeLanguage[] }) {
  if (items.length === 0) return null;
  return (
    <DetailSection title="Languages">
      <p className="text-sm text-ink-2">
        {items
          .map((item) =>
            [item.language, item.proficiency].filter(Boolean).join(" - "),
          )
          .join(", ")}
      </p>
    </DetailSection>
  );
}

function AdditionalSectionList({
  items,
}: {
  items: ResumeAdditionalSection[];
}) {
  if (items.length === 0) return null;
  return (
    <>
      {items.map((item, index) => (
        <DetailSection key={index} title={item.heading || "Additional section"}>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">
            {item.content}
          </p>
        </DetailSection>
      ))}
    </>
  );
}

function ContactBlock({ contact }: { contact: ResumeContact }) {
  const parts = [contact.email, contact.phone, contact.location].filter(Boolean);
  if (!contact.name && parts.length === 0 && contact.links.length === 0) {
    return null;
  }
  return (
    <div className="rounded-card border border-line bg-card p-4">
      {contact.name ? (
        <p className="text-base font-semibold text-ink">{contact.name}</p>
      ) : null}
      {parts.length > 0 ? (
        <p className="mt-0.5 text-sm text-ink-2">{parts.join(" - ")}</p>
      ) : null}
      <LinkList links={contact.links} />
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-ink-2">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

function LinkList({ links }: { links: { label: string; url: string }[] }) {
  if (links.length === 0) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-2">
      {links.map((link, index) => {
        const href = safeHref(link.url);
        return href ? (
          <a
            key={index}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
          >
            {link.label || link.url}
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        ) : (
          <span key={index} className="text-xs text-ink-2">
            {link.label || link.url}
          </span>
        );
      })}
    </div>
  );
}

function safeHref(url: string): string | null {
  const trimmed = url.trim();
  try {
    const parsed = new URL(trimmed);
    if (["http:", "https:", "mailto:"].includes(parsed.protocol)) {
      return parsed.toString();
    }
  } catch {
    return null;
  }
  return null;
}
