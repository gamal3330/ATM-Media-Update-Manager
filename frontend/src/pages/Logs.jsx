import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Filter,
  RefreshCw,
  Search,
  ShieldCheck,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiDate, parseApiDate } from "../api/time";

const sourceOptions = [
  ["all", "الكل"],
  ["agent", "Agent"],
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

function getAuditActionLabel(action) {
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
    user_create: "إنشاء مستخدم",
    user_delete: "حذف مستخدم",
    user_update: "تعديل مستخدم",
  };
  return labels[action] || action || "إجراء";
}

function buildAgentRecord(log) {
  const atm = log.atm || {};
  const context = log.context && typeof log.context === "object" ? log.context : {};
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
    title,
    subtitle: log.message,
    level: normalizeText(log.level) || "info",
    levelMeta,
    details: log.context,
    atm: {
      id: atmId,
      name: atmName,
      branch: atmBranch,
      ip: atmIp,
      known: atmId !== "-",
    },
    target: [atmBranch, atmIp].filter(Boolean).join(" · "),
    occurredAt: log.created_at,
    searchText: [atmId, atmName, atmBranch, atmIp, log.level, log.message, stringifyDetails(log.context)].join(" "),
  };
}

function buildAuditRecord(log) {
  const actor = `${log.actor_type || "-"}: ${log.actor_id || "-"}`;
  const target = [log.entity_type, log.entity_id].filter(Boolean).join(" · ");
  return {
    id: `audit-${log.id}`,
    source: "audit",
    sourceLabel: "Audit",
    icon: ShieldCheck,
    title: getAuditActionLabel(log.action),
    subtitle: actor,
    level: "audit",
    levelMeta: {
      label: "Audit",
      icon: ClipboardList,
      badge: "bg-sky-50 text-sky-700",
      border: "border-sky-200",
      dot: "bg-sky-500",
    },
    details: log.details,
    target,
    occurredAt: log.created_at,
    searchText: [log.action, actor, target, stringifyDetails(log.details)].join(" "),
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

function LogTimeline({ records }) {
  if (records.length === 0) return <EmptyState />;

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="divide-y divide-slate-100">
        {records.map((record) => {
          const Icon = record.icon;
          const BadgeIcon = record.levelMeta.icon;
          const detailsText = stringifyDetails(record.details);
          const hasDetails = Boolean(detailsText);

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

                {record.source === "agent" && (
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
                  <span>{formatApiDate(record.occurredAt)}</span>
                </div>

                {hasDetails && (
                  <details className="group mt-3">
                    <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                      <span>التفاصيل</span>
                    </summary>
                    <pre className="mt-2 max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-xs leading-5 text-slate-100" dir="ltr">
                      {detailsText}
                    </pre>
                  </details>
                )}
              </div>

              <div className="text-xs text-slate-500 md:text-left">
                <div>{formatApiDate(record.occurredAt)}</div>
                <div className="mt-1 font-medium text-slate-600">{record.sourceLabel}</div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

export default function Logs({ logs, auditLogs, onRefresh }) {
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [levelFilter, setLevelFilter] = useState("all");

  const records = useMemo(() => {
    const agentRecords = (Array.isArray(logs) ? logs : []).map(buildAgentRecord);
    const auditRecords = (Array.isArray(auditLogs) ? auditLogs : []).map(buildAuditRecord);
    return [...agentRecords, ...auditRecords].sort((first, second) => {
      const firstDate = parseApiDate(first.occurredAt)?.getTime() || 0;
      const secondDate = parseApiDate(second.occurredAt)?.getTime() || 0;
      return secondDate - firstDate;
    });
  }, [logs, auditLogs]);

  const stats = useMemo(() => {
    const agentLogs = Array.isArray(logs) ? logs : [];
    return {
      total: records.length,
      errors: agentLogs.filter((log) => normalizeText(log.level) === "error").length,
      warnings: agentLogs.filter((log) => normalizeText(log.level) === "warning").length,
      audit: Array.isArray(auditLogs) ? auditLogs.length : 0,
    };
  }, [logs, auditLogs, records.length]);

  const filteredRecords = useMemo(() => {
    const needle = normalizeText(query);
    return records.filter((record) => {
      if (sourceFilter !== "all" && record.source !== sourceFilter) return false;
      if (levelFilter !== "all" && record.source === "agent" && record.level !== levelFilter) return false;
      if (levelFilter !== "all" && record.source !== "agent") return false;
      if (!needle) return true;
      return normalizeText(record.searchText).includes(needle);
    });
  }, [levelFilter, query, records, sourceFilter]);

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">السجلات</h1>
          <p className="text-sm text-slate-500">Agent و Audit في مسار زمني واحد</p>
        </div>
        <button
          onClick={onRefresh}
          className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
          title="تحديث السجلات"
        >
          <RefreshCw size={17} />
          <span>تحديث</span>
        </button>
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatPill label="كل السجلات" value={stats.total} icon={Activity} />
        <StatPill label="أخطاء Agent" value={stats.errors} icon={XCircle} tone={stats.errors ? "rose" : "emerald"} />
        <StatPill label="تحذيرات Agent" value={stats.warnings} icon={AlertTriangle} tone={stats.warnings ? "amber" : "emerald"} />
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
      </div>

      <LogTimeline records={filteredRecords} />
    </section>
  );
}
