export const ONLINE_THRESHOLD_MS = 5 * 60 * 1000;
export const APP_TIME_ZONE = "Asia/Aden";

const API_DATE_FORMATTER = new Intl.DateTimeFormat("en-GB", {
  timeZone: APP_TIME_ZONE,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});

function dateParts(date) {
  return Object.fromEntries(API_DATE_FORMATTER.formatToParts(date).map((part) => [part.type, part.value]));
}

function numericText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : value;
}

export function parseApiDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;

  const text = String(value);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const normalized = hasTimezone ? text : `${text.replace(" ", "T")}Z`;
  const parsed = new Date(normalized);

  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const LOCAL_WALL_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/;

function hasExplicitTimezone(value) {
  return /(?:Z|[+-]\d{2}:?\d{2})$/.test(String(value || ""));
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatWallDateParts(year, month, day, hour, minute, second = "00") {
  const hour24 = Number(hour);
  const hour12 = hour24 % 12 || 12;
  const period = hour24 >= 12 ? "م" : "ص";
  return `${numericText(year)}/${numericText(month)}/${numericText(day)} ${period} ${hour12}:${pad2(minute)}:${pad2(second)}`;
}

export function parseLocalWallDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (hasExplicitTimezone(value)) return parseApiDate(value);

  const match = LOCAL_WALL_DATE_RE.exec(String(value));
  if (!match) return parseApiDate(value);

  const [, year, month, day, hour, minute, second = "00"] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatLocalWallDate(value) {
  if (!value) return "-";
  if (value instanceof Date || hasExplicitTimezone(value)) return formatApiDate(value);

  const match = LOCAL_WALL_DATE_RE.exec(String(value));
  if (!match) return formatApiDate(value);

  const [, year, month, day, hour, minute, second = "00"] = match;
  return formatWallDateParts(year, month, day, hour, minute, second);
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
  if (!parsed) return "-";

  const parts = dateParts(parsed);
  if (!parts.year || !parts.month || !parts.day || !parts.hour || !parts.minute || !parts.second) {
    return API_DATE_FORMATTER.format(parsed);
  }

  const period = String(parts.dayPeriod || "").toLowerCase().includes("p") ? "م" : "ص";
  return `${numericText(parts.year)}/${numericText(parts.month)}/${numericText(parts.day)} ${period} ${numericText(parts.hour)}:${parts.minute}:${parts.second}`;
}
