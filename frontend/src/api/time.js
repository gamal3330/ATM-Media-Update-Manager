export const ONLINE_THRESHOLD_MS = 5 * 60 * 1000;

export function parseApiDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;

  const text = String(value);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const normalized = hasTimezone ? text : `${text.replace(" ", "T")}Z`;
  const parsed = new Date(normalized);

  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function isRecentlyOnline(atm, thresholdMs = ONLINE_THRESHOLD_MS) {
  if (typeof atm?.is_online === "boolean") return atm.is_online;
  const lastSeen = parseApiDate(atm?.last_seen);
  if (!lastSeen) return false;
  return Date.now() - lastSeen.getTime() < thresholdMs;
}

export function formatLastSeenAge(atm) {
  if (typeof atm?.seconds_since_last_seen !== "number") return "لا يوجد اتصال";
  const seconds = atm.seconds_since_last_seen;
  if (seconds < 60) return `قبل ${seconds} ثانية`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `قبل ${minutes} دقيقة`;
  const hours = Math.floor(minutes / 60);
  return `قبل ${hours} ساعة`;
}

export function formatApiDate(value) {
  const parsed = parseApiDate(value);
  return parsed ? parsed.toLocaleString() : "-";
}
