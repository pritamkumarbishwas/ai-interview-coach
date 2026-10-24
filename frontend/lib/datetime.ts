export const IST_TZ = "Asia/Kolkata";

const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/**
 * Parses a timestamp from the API as an absolute instant.
 *
 * The backend sends ISO-8601 with an explicit offset (`+05:30`). Older values
 * may lack one, and `new Date()` would then read them as local time — so a
 * missing offset is treated as UTC by appending `Z`.
 */
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const normalized = HAS_TIMEZONE.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Session-relative mm:ss for a stored timestamp. */
export function formatElapsed(
  startedAt: string | null | undefined,
  at: string | null | undefined,
): string {
  const started = parseApiDate(startedAt);
  const moment = parseApiDate(at);
  if (!started || !moment) return "";
  const total = Math.max(
    0,
    Math.floor((moment.getTime() - started.getTime()) / 1000),
  );
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function formatDate(value: string): string {
  const date = parseApiDate(value);
  if (!date) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: IST_TZ,
  });
}

export function formatDateTime(value: string): string {
  const date = parseApiDate(value);
  if (!date) return "";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: IST_TZ,
  });
}

export function formatTime(value: string): string {
  const date = parseApiDate(value);
  if (!date) return "";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: IST_TZ,
  });
}
