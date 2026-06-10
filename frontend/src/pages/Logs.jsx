import {
  Activity,
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Filter,
  RefreshCw,
  Search,
  ShieldCheck,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiDate, formatLocalWallDate, parseApiDate, parseLocalWallDate } from "../api/time";

const LOG_FETCH_LIMIT = 100;
const INITIAL_RENDER_LIMIT = 60;
const RENDER_INCREMENT = 60;

const sourceOptions = [
  ["all", "الكل"],
  ["agent", "Agent"],
  ["journal", "Journal"],
  ["audit", "Audit"],
];

const levelOptions = [
  ["all", "كل المستويات"],
  ["error", "Error"],
  ["warning", "Warning"],
  ["info", "Info"],
];

function normalizeText(value) {
  return String(value || "").toLowerCase().trim();
}

function stringifyDetails(details) {
  if (!details || typeof details !== "object") return "";
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return "";
  }
}

function compactSearchDetails(details) {
  if (!details || typeof details !== "object") return "";
  try {
    return JSON.stringify(details).slice(0, 500);
  } catch {
    return "";
  }
}

function hasMeaningfulDetails(details) {
  if (!details) return false;
  if (typeof details !== "object") return Boolean(String(details));
  return Object.keys(details).length > 0;
}

function getLevelMeta(level) {
  const value = normalizeText(level);
  if (value === "error") {
    return {
      label: "Error",
      icon: XCircle,
      badge: "bg-rose-50 text-rose-700",
      border: "border-rose-200",
      dot: "bg-rose-500",
    };
  }
  if (value === "warning") {
    return {
      label: "Warning",
      icon: AlertTriangle,
      badge: "bg-amber-50 text-amber-700",
      border: "border-amber-200",
      dot: "bg-amber-500",
    };
  }
  return {
    label: value || "Info",
    icon: CheckCircle2,
    badge: "bg-emerald-50 text-emerald-700",
    border: "border-slate-200",
    dot: "bg-slate-400",
  };
}

function cashAlertLabel(alertType) {
  const labels = {
    CASH_LOW: "انخفاض النقد",
    CASH_CRITICAL: "النقد في مستوى حرج",
    CASH_EMPTY: "انتهاء النقد",
    REJECT_BIN_HIGH: "صندوق المرفوضات قريب من الامتلاء",
    REJECT_BIN_FULL: "صندوق المرفوضات ممتلئ",
    RETRACT_OCCURRED: "تم رصد نقد مسترجع",
    CASSETTE_HEALTH: "حالة كاسيت غير طبيعية",
    CURRENCY_MISMATCH: "اختلاف العملة",
    DENOMINATION_MISMATCH: "اختلاف الفئة",
    CONFIG_PENDING: "بانتظار تطبيق الإعدادات",
  };
  return labels[alertType] || alertType || "تنبيه نقد";
}

function cashAlertSummary(action, details) {
  if (action !== "cash_alert_opened" || !details || typeof details !== "object") return null;

  const alertType = details.alert_type || "";
  const unitNo = Number(details.unit_no || 0);
  const currentCount = Number(details.current_count || 0);
  const unitLabel = unitNo > 0 ? `كاسيت ${unitNo}` : "صندوق عام";
  const countText = Number.isFinite(currentCount) ? `${currentCount} ورقة` : "-";
  const title = cashAlertLabel(alertType);

  let subtitle = `تم فتح تنبيه نقد: ${title}`;
  if (alertType === "RETRACT_OCCURRED") {
    subtitle = `تم رصد ${countText} في صندوق النقد المسترجع.`;
  } else if (alertType === "REJECT_BIN_FULL") {
    subtitle = `صندوق المرفوضات ممتلئ بعدد ${countText}.`;
  } else if (alertType === "REJECT_BIN_HIGH") {
    subtitle = `صندوق المرفوضات قريب من الامتلاء بعدد ${countText}.`;
  } else if (alertType === "CASH_EMPTY") {
    subtitle = `${unitLabel} انتهى النقد فيه.`;
  } else if (alertType === "CASH_LOW" || alertType === "CASH_CRITICAL") {
    subtitle = `${unitLabel}: الرصيد الحالي ${countText}.`;
  }

  return {
    title,
    subtitle,
    items: [
      ["نوع التنبيه", title],
      ["الصندوق", unitLabel],
      ["العدد الحالي", countText],
    ],
  };
}

const cdmStatusLabels = {
  ONLINE: "جاهز",
  BUSY: "مشغول مؤقتًا",
  OFFLINE: "غير متصل",
  POWEROFF: "مطفأ",
  NODEVICE: "غير متاح",
  HWERROR: "خطأ عتادي",
  FRAUDATTEMPT: "محاولة عبث",
  POTENTIALFRAUD: "اشتباه عبث",
  OPEN: "مفتوح",
  CLOSED: "مغلق",
  JAMMED: "منحشر",
};

function isUnknownXfsStatus(value) {
  return typeof value === "string" && value.startsWith("UNKNOWN_");
}

function friendlyStatus(value) {
  if (!value) return "";
  const normalized = String(value).toUpperCase();
  if (cdmStatusLabels[normalized]) return cdmStatusLabels[normalized];
  if (isUnknownXfsStatus(normalized)) return "غير معروف من مزود XFS";
  return value;
}

function statusDetail(value) {
  if (!value) return "";
  const friendly = friendlyStatus(value);
  return isUnknownXfsStatus(String(value).toUpperCase()) ? `${friendly} (${value})` : friendly;
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 60) return `${Math.round(value)} ثانية`;
  return `${Math.floor(value / 60)} دقيقة ${Math.round(value % 60)} ثانية`;
}

function agentEventSummary(context, fallbackMessage) {
  if (!context || typeof context !== "object") return null;
  const eventType = context.event_type || "";
  if (eventType.startsWith("JOURNAL_")) {
    const title = context.journal_event_type
      ? `Journal ${String(context.journal_event_type).replaceAll("_", " ").toLowerCase()}`
      : "Journal event";
    const details = context.details && typeof context.details === "object" ? context.details : {};
    const amount = context.amount ? `${context.amount} ${context.currency || ""}`.trim() : "";
    const cassetteOutputs = Array.isArray(context.cassette_outputs)
      ? context.cassette_outputs
          .map((item) => `CAS ${item.cassette_no}: out ${item.out}, reject ${item.reject}, deno ${item.denomination}`)
          .join(" | ")
      : "";
    const subtitleParts = [
      context.transaction_type,
      amount,
      context.rrn ? `RRN ${context.rrn}` : "",
      details.completed === true ? "completed" : "",
      details.take_cash_timeout ? "cash timeout warning" : "",
    ].filter(Boolean);
    const items = [
      ["Event", context.journal_event_type || eventType],
      context.occurred_at ? ["Occurred at", formatApiDate(context.occurred_at)] : null,
      context.transaction_serial ? ["Serial", context.transaction_serial] : null,
      context.transaction_type ? ["Transaction type", context.transaction_type] : null,
      amount ? ["Amount", amount] : null,
      context.rrn ? ["RRN", context.rrn] : null,
      context.stan ? ["STAN", context.stan] : null,
      context.auth_code ? ["Auth code", context.auth_code] : null,
      context.card_masked ? ["Card", context.card_masked] : null,
      context.receipt_date ? ["Receipt date", context.receipt_date] : null,
      cassetteOutputs ? ["Cassette outputs", cassetteOutputs] : null,
      context.file_path ? ["File", context.file_path] : null,
      context.line_number ? ["Line", context.line_number] : null,
    ].filter(Boolean);
    return {
      title,
      subtitle: subtitleParts.join(" | ") || fallbackMessage,
      items,
    };
  }
  const state = context.state && typeof context.state === "object" ? context.state : {};
  const siu = context.siu && typeof context.siu === "object" ? context.siu : {};
  const labels = {
    CDM_SHUTTER_OPENED: "فتح Shutter",
    CDM_SHUTTER_CLOSED: "إغلاق Shutter",
    CDM_SHUTTER_JAMMED: "انحشار Shutter",
    CDM_SAFE_DOOR_OPENED: "فتح باب الخزنة",
    CDM_SAFE_DOOR_CLOSED: "إغلاق باب الخزنة",
    CDM_DEVICE_ATTENTION: "حالة وحدة النقد تحتاج متابعة",
    CDM_DEVICE_ONLINE: "وحدة النقد جاهزة",
    CDM_STATUS_READ_FAILED: "قراءة حالة CDM غير متاحة",
    CASH_CASSETTE_REMOVED: "تمت إزالة كاسيت",
    CASH_CASSETTE_INSERTED: "تم تركيب كاسيت",
    CASH_CASSETTE_STATUS_CHANGED: "تغيرت حالة كاسيت",
    SIU_STATUS_READ_FAILED: "تعذر قراءة حساسات SIU",
    SIU_CABINET_DOOR_OPENED: "فتح باب الصراف العلوي",
    SIU_CABINET_DOOR_CLOSED: "إغلاق باب الصراف العلوي",
    SIU_SAFE_DOOR_OPENED: "فتح باب الخزنة",
    SIU_SAFE_DOOR_CLOSED: "إغلاق باب الخزنة",
    SIU_VANDAL_SHIELD_OPENED: "فتح Vandal Shield",
    SIU_VANDAL_SHIELD_CLOSED: "إغلاق Vandal Shield",
    SIU_OPERATOR_SWITCH_CHANGED: "تغير وضع مفتاح التشغيل",
    SIU_TAMPER_TRIGGERED: "حساس العبث يعمل",
    SIU_INTERNAL_TAMPER_TRIGGERED: "حساس العبث الداخلي يعمل",
    SIU_SEISMIC_TRIGGERED: "حساس الاهتزاز يعمل",
    SIU_HEAT_TRIGGERED: "حساس الحرارة يعمل",
    SIU_PROXIMITY_PRESENT: "تم رصد اقتراب",
    SIU_DEVICE_ATTENTION: "حالة SIU تحتاج متابعة",
    SIU_DEVICE_ONLINE: "SIU عاد Online",
  };
  const title = labels[eventType];
  if (!title) return null;

  const cassetteNo = context.cassette_no ? `كاسيت ${context.cassette_no}` : "";
  const current = context.state && typeof context.state === "string" ? context.state : "";
  const previous = context.previous_state || "";
  const busyDuration = formatDuration(context.busy_duration_seconds);
  const displayTitle =
    eventType === "CDM_DEVICE_ONLINE" && String(previous).toUpperCase() === "BUSY"
      ? "وحدة النقد عادت جاهزة بعد انشغال مؤقت"
      : title;
  const subtitleParts = [];
  if (eventType === "CDM_STATUS_READ_FAILED" && context.cash_snapshot_sent) {
    subtitleParts.push("قراءة الصناديق مستمرة");
  }
  if (eventType === "CDM_STATUS_READ_FAILED" && context.error) {
    subtitleParts.push(`السبب: ${context.error}`);
  }
  if (cassetteNo) subtitleParts.push(cassetteNo);
  if (previous || current) subtitleParts.push([friendlyStatus(previous), friendlyStatus(current)].filter(Boolean).join(" → "));
  if (busyDuration) subtitleParts.push(`استمر ${busyDuration}`);
  if (state.device_status) subtitleParts.push(`CDM: ${friendlyStatus(state.device_status)}`);
  if (state.safe_door_status) subtitleParts.push(`باب الخزنة: ${friendlyStatus(state.safe_door_status)}`);
  if (state.shutter_status && !isUnknownXfsStatus(String(state.shutter_status).toUpperCase())) {
    subtitleParts.push(`Shutter: ${friendlyStatus(state.shutter_status)}`);
  }
  if (siu.device_status) subtitleParts.push(`SIU: ${friendlyStatus(siu.device_status)}`);

  const items = [
    ["نوع الحدث", displayTitle],
    previous ? ["الحالة السابقة", statusDetail(previous)] : null,
    current ? ["الحالة الحالية", statusDetail(current)] : null,
    busyDuration ? ["مدة الانشغال", busyDuration] : null,
    state.device_status ? ["CDM", statusDetail(state.device_status)] : null,
    state.shutter_status ? ["Shutter", statusDetail(state.shutter_status)] : null,
    state.safe_door_status ? ["Safe door", statusDetail(state.safe_door_status)] : null,
    state.transport_status ? ["Transport", statusDetail(state.transport_status)] : null,
    siu.device_status ? ["SIU", statusDetail(siu.device_status)] : null,
    context.error ? ["سبب الفشل", context.error] : null,
    context.xfs_profile ? ["XFS Profile", context.xfs_profile] : null,
    context.xfs_logical_service ? ["Logical Service", context.xfs_logical_service] : null,
    context.cash_snapshot_sent ? ["قراءة النقد", "نجحت قبل فحص حالة CDM"] : null,
    context.port ? ["الحساس", context.port] : null,
    context.cassette_no ? ["الكاسيت", context.cassette_no] : null,
  ].filter(Boolean);

  return {
    title: displayTitle,
    subtitle: subtitleParts.join(" · ") || fallbackMessage,
    items,
  };
}

function getAuditActionLabel(action, details) {
  const cashSummary = cashAlertSummary(action, details);
  if (cashSummary) return cashSummary.title;

  const labels = {
    atm_create: "إنشاء صراف",
    atm_delete: "حذف صراف",
    atm_regenerate_api_key: "توليد API Key",
    atm_update: "تعديل صراف",
    cash_threshold_update: "تعديل حدود النقد",
    login: "تسجيل دخول",
    notification_recipient_update: "تعديل مستلمي التنبيهات",
    notification_settings_update: "تعديل إعدادات التنبيهات",
    package_assign: "تعيين تحديث",
    package_create: "إنشاء حزمة",
    package_delete: "حذف حزمة",
    cash_alert_opened: "فتح تنبيه نقد",
    user_create: "إنشاء مستخدم",
    user_delete: "حذف مستخدم",
    user_update: "تعديل مستخدم",
  };
  return labels[action] || action || "إجراء";
}

function buildAgentRecord(log) {
  const atm = log.atm || {};
  const context = log.context && typeof log.context === "object" ? log.context : {};
  const eventSummary = agentEventSummary(context, log.message);
  const atmId = atm.atm_id || context.atm_id || "-";
  const atmName = atm.name || "";
  const atmBranch = atm.branch || "";
  const atmIp = atm.vpn_ip || "";
  const levelMeta = getLevelMeta(log.level);
  const title = atmId === "-" ? "صراف غير محدد" : atmName ? `${atmName} · ${atmId}` : `صراف ${atmId}`;

  return {
    id: `agent-${log.id}`,
    source: "agent",
    sourceLabel: "Agent",
    icon: TerminalSquare,
    title: eventSummary?.title || title,
    subtitle: eventSummary?.subtitle || log.message,
    level: normalizeText(log.level) || "info",
    levelMeta,
    details: log.context,
    detailItems: eventSummary?.items || [],
    atm: {
      id: atmId,
      name: atmName,
      branch: atmBranch,
      ip: atmIp,
      known: atmId !== "-",
    },
    target: [atmBranch, atmIp].filter(Boolean).join(" · "),
    occurredAt: log.created_at,
    searchText: [atmId, atmName, atmBranch, atmIp, log.level, eventSummary?.title, log.message, compactSearchDetails(log.context)].join(" "),
  };
}

function buildAuditRecord(log) {
  const actor = `${log.actor_type || "-"}: ${log.actor_id || "-"}`;
  const target = [log.entity_type, log.entity_id].filter(Boolean).join(" · ");
  const alertSummary = cashAlertSummary(log.action, log.details);
  return {
    id: `audit-${log.id}`,
    source: "audit",
    sourceLabel: "Audit",
    icon: ShieldCheck,
    title: alertSummary?.title || getAuditActionLabel(log.action, log.details),
    subtitle: alertSummary?.subtitle || actor,
    level: "audit",
    levelMeta: {
      label: "Audit",
      icon: ClipboardList,
      badge: "bg-sky-50 text-sky-700",
      border: "border-sky-200",
      dot: "bg-sky-500",
    },
    details: log.details,
    detailItems: alertSummary?.items || [],
    target,
    occurredAt: log.created_at,
    searchText: [log.action, actor, target, alertSummary?.title, alertSummary?.subtitle, compactSearchDetails(log.details)].join(" "),
  };
}

function journalEventTitle(eventType) {
  const value = String(eventType || "").replaceAll("_", " ").toLowerCase();
  return value ? `Journal ${value}` : "Journal event";
}

function formatRecordDate(record) {
  return record.source === "journal" ? formatLocalWallDate(record.occurredAt) : formatApiDate(record.occurredAt);
}

function parseRecordDate(record) {
  return record.source === "journal" ? parseLocalWallDate(record.occurredAt) : parseApiDate(record.occurredAt);
}

function buildJournalRecord(event) {
  const atm = event.atm || {};
  const details = event.details_json && typeof event.details_json === "object" ? event.details_json : {};
  const cassetteOutputs = Array.isArray(event.cassette_outputs_json)
    ? event.cassette_outputs_json
        .map((item) => `CAS ${item.cassette_no}: out ${item.out}, reject ${item.reject}, deno ${item.denomination}`)
        .join(" | ")
    : "";
  const amount = event.amount ? `${event.amount} ${event.currency || ""}`.trim() : "";
  const title = journalEventTitle(event.event_type);
  const subtitleParts = [
    event.transaction_type,
    amount,
    event.rrn ? `RRN ${event.rrn}` : "",
    details.completed === true ? "completed" : "",
    details.take_cash_timeout ? "cash timeout warning" : "",
  ].filter(Boolean);
  const atmId = atm.atm_id || "-";
  const atmName = atm.name || "";
  const atmBranch = atm.branch || "";
  const atmIp = atm.vpn_ip || "";
  const levelMeta = getLevelMeta(event.severity);
  const journalOccurredAt = event.occurred_at || event.received_at;
  const detailItems = [
    ["Event", event.event_type],
    ["وقت الجورنال", formatLocalWallDate(journalOccurredAt)],
    event.received_at ? ["وقت وصول النظام", formatApiDate(event.received_at)] : null,
    event.transaction_serial ? ["Serial", event.transaction_serial] : null,
    event.transaction_type ? ["Transaction type", event.transaction_type] : null,
    amount ? ["Amount", amount] : null,
    event.rrn ? ["RRN", event.rrn] : null,
    event.stan ? ["STAN", event.stan] : null,
    event.auth_code ? ["Auth code", event.auth_code] : null,
    event.card_masked ? ["Card", event.card_masked] : null,
    event.receipt_date ? ["Receipt date", event.receipt_date] : null,
    cassetteOutputs ? ["Cassette outputs", cassetteOutputs] : null,
    event.file_path ? ["File", event.file_path] : null,
    event.line_number ? ["Line", event.line_number] : null,
  ].filter(Boolean);

  return {
    id: `journal-${event.id}`,
    source: "journal",
    sourceLabel: "Journal",
    icon: ClipboardList,
    title,
    subtitle: subtitleParts.join(" | ") || event.message,
    level: normalizeText(event.severity) || "info",
    levelMeta,
    details: {
      event_type: event.event_type,
      source: event.source,
      occurred_at: event.occurred_at,
      received_at: event.received_at,
      transaction_serial: event.transaction_serial,
      transaction_type: event.transaction_type,
      amount: event.amount,
      currency: event.currency,
      rrn: event.rrn,
      stan: event.stan,
      auth_code: event.auth_code,
      card_masked: event.card_masked,
      receipt_date: event.receipt_date,
      cassette_outputs: event.cassette_outputs_json,
      details,
      file_path: event.file_path,
      line_number: event.line_number,
    },
    detailItems,
    atm: {
      id: atmId,
      name: atmName,
      branch: atmBranch,
      ip: atmIp,
      known: atmId !== "-",
    },
    target: [atmBranch, atmIp].filter(Boolean).join(" Â· "),
    occurredAt: journalOccurredAt,
    searchText: [
      "journal",
      atmId,
      atmName,
      atmBranch,
      atmIp,
      event.event_type,
      event.transaction_serial,
      event.transaction_type,
      event.amount,
      event.currency,
      event.rrn,
      event.stan,
      event.auth_code,
      event.card_masked,
      event.file_path,
      compactSearchDetails(details),
    ].join(" "),
  };
}

function StatPill({ label, value, icon: Icon, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    sky: "border-sky-200 bg-sky-50 text-sky-900",
  };

  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <Icon size={17} className="opacity-70" />
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none">{value}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-12 text-center">
      <ClipboardList className="mx-auto text-slate-400" size={28} />
      <div className="mt-3 font-semibold text-slate-900">لا توجد سجلات مطابقة</div>
      <div className="mt-1 text-sm text-slate-500">غيّر البحث أو الفلتر لعرض نتائج أخرى.</div>
    </div>
  );
}

function RecordDetails({ record }) {
  const [open, setOpen] = useState(false);
  const hasStructuredDetails = Array.isArray(record.detailItems) && record.detailItems.length > 0;
  const hasRawDetails = hasMeaningfulDetails(record.details);
  if (!hasStructuredDetails && !hasRawDetails) return null;

  const detailsText = open && !hasStructuredDetails ? stringifyDetails(record.details) : "";

  return (
    <details className="group mt-3" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
        <span>Ø§Ù„ØªÙØ§ØµÙŠÙ„</span>
      </summary>
      {hasStructuredDetails ? (
        <div className="mt-2 grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-3">
          {record.detailItems.map(([label, value]) => (
            <div key={label} className="rounded-lg bg-white px-3 py-2">
              <div className="text-xs font-medium text-slate-500">{label}</div>
              <div className="mt-1 font-semibold text-slate-950">{value}</div>
            </div>
          ))}
        </div>
      ) : (
        <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-100" dir="ltr">
          {detailsText}
        </pre>
      )}
    </details>
  );
}

function LogTimeline({ records }) {
  if (records.length === 0) return <EmptyState />;

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="divide-y divide-slate-100">
        {records.map((record) => {
          const Icon = record.icon;
          const BadgeIcon = record.levelMeta.icon;
          const hasStructuredDetails = Array.isArray(record.detailItems) && record.detailItems.length > 0;
          const detailsText = hasStructuredDetails ? "" : stringifyDetails(record.details);
          const hasDetails = hasStructuredDetails || hasMeaningfulDetails(record.details);

          return (
            <article key={record.id} className="grid gap-3 px-4 py-4 md:grid-cols-[auto_1fr_auto]">
              <div className="flex items-start gap-3 md:block">
                <span className={`mt-1 block h-2.5 w-2.5 rounded-full ${record.levelMeta.dot}`} />
                <Icon size={18} className="mt-0.5 text-slate-500 md:hidden" />
              </div>

              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Icon size={17} className="hidden text-slate-500 md:inline" />
                  <span className="truncate font-semibold text-slate-950">{record.title}</span>
                  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${record.levelMeta.badge}`}>
                    <BadgeIcon size={12} />
                    {record.levelMeta.label}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {record.sourceLabel}
                  </span>
                </div>

                {(record.source === "agent" || record.source === "journal") && (
                  <div
                    className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
                      record.atm?.known
                        ? "border-slate-200 bg-slate-50 text-slate-700"
                        : "border-amber-200 bg-amber-50 text-amber-800"
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-950">
                        {record.atm?.known ? record.atm.name || `صراف ${record.atm.id}` : "صراف غير محدد"}
                      </span>
                      <span className="rounded-full bg-white px-2 py-0.5 font-mono text-xs text-slate-700" dir="ltr">
                        ATM {record.atm?.id || "-"}
                      </span>
                      {record.atm?.branch && (
                        <span className="rounded-full bg-white px-2 py-0.5 text-xs text-slate-600">{record.atm.branch}</span>
                      )}
                      {record.atm?.ip && (
                        <span className="rounded-full bg-white px-2 py-0.5 font-mono text-xs text-slate-600" dir="ltr">
                          {record.atm.ip}
                        </span>
                      )}
                    </div>
                    {!record.atm?.known && (
                      <div className="mt-1 text-xs">
                        هذا السجل قديم أو غير مربوط بصراف في قاعدة البيانات. افتح التفاصيل للبحث عن atm_id إن وجد.
                      </div>
                    )}
                  </div>
                )}

                {record.subtitle && <div className="mt-1 break-words text-sm leading-6 text-slate-700">{record.subtitle}</div>}

                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  {record.target && <span className="rounded-full bg-slate-50 px-2 py-1">{record.target}</span>}
                  <span>{formatRecordDate(record)}</span>
                </div>

                {hasDetails && (
                  <details className="group mt-3">
                    <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                      <span>التفاصيل</span>
                    </summary>
                    {hasStructuredDetails ? (
                      <div className="mt-2 grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-3">
                        {record.detailItems.map(([label, value]) => (
                          <div key={label} className="rounded-lg bg-white px-3 py-2">
                            <div className="text-xs font-medium text-slate-500">{label}</div>
                            <div className="mt-1 font-semibold text-slate-950">{value}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-100" dir="ltr">
                        {detailsText}
                      </pre>
                    )}
                  </details>
                )}
              </div>

              <div className="text-xs text-slate-500 md:text-left">
                <div>{formatRecordDate(record)}</div>
                <div className="mt-1 font-medium text-slate-600">{record.sourceLabel}</div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export default function Logs({ logs, auditLogs, journalLogs, atms, loading = false, onRefresh }) {
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("agent");
  const [levelFilter, setLevelFilter] = useState("all");
  const [atmFilter, setAtmFilter] = useState("");
  const [fromAt, setFromAt] = useState("");
  const [toAt, setToAt] = useState("");
  const [visibleCount, setVisibleCount] = useState(INITIAL_RENDER_LIMIT);
  const journalCanLoad = Boolean(atmFilter);

  const records = useMemo(() => {
    const agentRecords = (Array.isArray(logs) ? logs : []).map(buildAgentRecord);
    const auditRecords = (Array.isArray(auditLogs) ? auditLogs : []).map(buildAuditRecord);
    const journalRecords = (Array.isArray(journalLogs) ? journalLogs : []).map(buildJournalRecord);
    return [...agentRecords, ...journalRecords, ...auditRecords].sort((first, second) => {
      const firstDate = parseRecordDate(first)?.getTime() || 0;
      const secondDate = parseRecordDate(second)?.getTime() || 0;
      return secondDate - firstDate;
    });
  }, [logs, auditLogs, journalLogs]);

  const stats = useMemo(() => {
    const agentLogs = Array.isArray(logs) ? logs : [];
    return {
      total: records.length,
      errors: agentLogs.filter((log) => normalizeText(log.level) === "error").length,
      warnings: agentLogs.filter((log) => normalizeText(log.level) === "warning").length,
      audit: Array.isArray(auditLogs) ? auditLogs.length : 0,
      journal: Array.isArray(journalLogs) ? journalLogs.length : 0,
    };
  }, [logs, auditLogs, journalLogs, records.length]);

  const filteredRecords = useMemo(() => {
    const needle = normalizeText(query);
    return records.filter((record) => {
      if (sourceFilter !== "all" && record.source !== sourceFilter) return false;
      if (levelFilter !== "all" && record.source === "audit") return false;
      if (levelFilter !== "all" && record.level !== levelFilter) return false;
      if (!needle) return true;
      return normalizeText(record.searchText).includes(needle);
    });
  }, [levelFilter, query, records, sourceFilter]);

  useEffect(() => {
    setVisibleCount(INITIAL_RENDER_LIMIT);
  }, [atmFilter, auditLogs, fromAt, journalLogs, levelFilter, logs, query, sourceFilter, toAt]);

  const visibleRecords = filteredRecords.slice(0, visibleCount);
  const hasMoreRecords = filteredRecords.length > visibleRecords.length;

  function currentServerFilters() {
    return {
      atmId: atmFilter,
      fromAt,
      toAt,
      source: sourceFilter,
      limit: LOG_FETCH_LIMIT,
    };
  }

  function applyServerFilters() {
    onRefresh(currentServerFilters());
  }

  function clearServerFilters() {
    setSourceFilter("agent");
    setAtmFilter("");
    setFromAt("");
    setToAt("");
    onRefresh({ source: "agent", limit: LOG_FETCH_LIMIT });
  }

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">السجلات</h1>
        </div>
        <button
          onClick={() => onRefresh(currentServerFilters())}
          disabled={loading}
          className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
          title="تحديث السجلات"
        >
          <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          <span>تحديث</span>
        </button>
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatPill label="كل السجلات" value={stats.total} icon={Activity} />
        <StatPill label="أخطاء Agent" value={stats.errors} icon={XCircle} tone={stats.errors ? "rose" : "emerald"} />
        <StatPill label="تحذيرات Agent" value={stats.warnings} icon={AlertTriangle} tone={stats.warnings ? "amber" : "emerald"} />
        <StatPill label="Journal" value={stats.journal} icon={ClipboardList} tone="sky" />
        <StatPill label="Audit" value={stats.audit} icon={ShieldCheck} tone="sky" />
      </div>

      <div className="mb-5 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              placeholder="بحث بالصراف، الرسالة، المستخدم أو الإجراء"
            />
          </label>

          <div className="inline-flex min-h-11 overflow-hidden rounded-lg border border-slate-300 bg-white">
            {sourceOptions.map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setSourceFilter(value);
                  if (value === "audit") setLevelFilter("all");
                }}
                className={`px-4 text-sm font-medium ${
                  sourceFilter === value ? "bg-teal-700 text-white" : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <label className="relative block">
            <Filter className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <select
              value={levelFilter}
              onChange={(event) => setLevelFilter(event.target.value)}
              disabled={sourceFilter === "audit"}
              className="focus-ring min-h-11 min-w-44 rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
            >
              {levelOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(220px,1.2fr)_minmax(180px,1fr)_minmax(180px,1fr)_auto_auto]">
          <label className="relative block">
            <TerminalSquare className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <select
              value={atmFilter}
              onChange={(event) => setAtmFilter(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="ATM"
            >
              <option value="">كل الصرافات</option>
              {(Array.isArray(atms) ? atms : []).map((atm) => (
                <option key={atm.atm_id} value={atm.atm_id}>
                  {atm.name ? `${atm.name} - ATM ${atm.atm_id}` : `ATM ${atm.atm_id}`}
                </option>
              ))}
            </select>
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={fromAt}
              onChange={(event) => setFromAt(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="From"
            />
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={toAt}
              onChange={(event) => setToAt(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="To"
            />
          </label>

          <button
            type="button"
            onClick={applyServerFilters}
            disabled={loading}
            className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
          >
            <Search size={17} className={loading ? "animate-pulse" : ""} />
            <span>بحث</span>
          </button>

          <button
            type="button"
            onClick={clearServerFilters}
            disabled={loading}
            className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <XCircle size={17} />
            <span>مسح</span>
          </button>
        </div>

        {(sourceFilter === "journal" || sourceFilter === "all") && !journalCanLoad && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            اختر صرافًا ثم اضغط بحث لتحميل سجلات Journal الخاصة به فقط.
          </div>
        )}
      </div>

      {loading && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-sm text-teal-800">
          <RefreshCw size={16} className="animate-spin" />
          <span>جاري تحميل السجلات</span>
        </div>
      )}

      <LogTimeline records={visibleRecords} />

      {hasMoreRecords && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={() => setVisibleCount((current) => current + RENDER_INCREMENT)}
            className="focus-ring inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            عرض المزيد ({filteredRecords.length - visibleRecords.length})
          </button>
        </div>
      )}
    </section>
  );
}
