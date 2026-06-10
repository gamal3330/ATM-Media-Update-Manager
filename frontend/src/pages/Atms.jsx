import {
  Activity,
  AlertCircle,
  ChevronDown,
  CheckCircle2,
  Clipboard,
  Clock3,
  KeyRound,
  Network,
  Plus,
  RefreshCw,
  Save,
  ScrollText,
  Search,
  Server,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  Trash2,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api, apiBaseUrl } from "../api/client";
import { formatApiDate, formatLastSeenAge, formatLocalWallDate, isRecentlyOnline } from "../api/time";

const currencyDefaults = {
  YER: { label: "يمني", denomination: 1000, low_threshold: 300, critical_threshold: 100 },
  SAR: { label: "سعودي", denomination: 100, low_threshold: 100, critical_threshold: 30 },
  USD: { label: "دولار", denomination: 100, low_threshold: 100, critical_threshold: 30 },
};
const currencyOptions = [
  ["YER", "يمني"],
  ["SAR", "سعودي"],
  ["USD", "دولار"],
];
const cassetteNumbers = [1, 2, 3, 4];
const xfsProfileDefaults = {
  ncr_aptra: "MediaDispenser1",
  grg: "CDM",
};
const xfsMsxfsPathDefaults = {
  grg: "C:\\Windows\\SysWOW64\\msxfs.dll",
};
const settingsFields = [
  ["media_path", "Media Path", "C:/ATM/Media"],
  ["backup_path", "Backup Path", "C:/ATM/Media_Backup"],
  ["temp_path", "Temp Path", "C:/ATM/Temp"],
  ["check_interval_seconds", "Media Check Interval", "300"],
  ["heartbeat_interval_seconds", "Heartbeat Interval", "60"],
];

function normalizeCashProvider(value, cashEnabled = false) {
  if (value === "xfs_cdm" || value === "vendor_cdm") return value;
  return "xfs_cdm";
}

const fields = [
  ["atm_id", "ATM ID", "ATM-001", 2],
  ["name", "الاسم", "صراف الفرع الرئيسي", 2],
  ["vpn_ip", "IP عبر VPN", "192.168.2.35", 3],
  ["branch", "الفرع", "lab1", 2],
];

function buildCashLayout(currencies = ["YER", "YER", "YER", "YER"]) {
  return cassetteNumbers.map((cassetteNo, index) => {
    const currency = currencies[index] || "YER";
    const defaults = currencyDefaults[currency] || currencyDefaults.YER;
    return {
      cassette_no: cassetteNo,
      currency,
      denomination: defaults.denomination,
      max_capacity: 2000,
      low_threshold: defaults.low_threshold,
      critical_threshold: defaults.critical_threshold,
    };
  });
}

function normalizeCashLayout(layout) {
  return cassetteNumbers.map((cassetteNo) => {
    const existing = Array.isArray(layout) ? layout.find((item) => Number(item.cassette_no) === cassetteNo) : null;
    const currency = currencyDefaults[existing?.currency] ? existing.currency : "YER";
    const defaults = currencyDefaults[currency];
    return {
      cassette_no: cassetteNo,
      currency,
      denomination: defaults.denomination,
      max_capacity: Number(existing?.max_capacity) || 2000,
      low_threshold: Number(existing?.low_threshold) || defaults.low_threshold,
      critical_threshold: Number(existing?.critical_threshold) || defaults.critical_threshold,
    };
  });
}

function updateCashLayoutCurrency(layout, cassetteNo, currency) {
  const defaults = currencyDefaults[currency] || currencyDefaults.YER;
  return normalizeCashLayout(layout).map((item) =>
    item.cassette_no === cassetteNo
      ? {
          ...item,
          currency,
          denomination: defaults.denomination,
          low_threshold: defaults.low_threshold,
          critical_threshold: defaults.critical_threshold,
        }
      : item,
  );
}

function buildEmptyForm() {
  return { atm_id: "", name: "", vpn_ip: "", branch: "", xfs_profile: "ncr_aptra", cash_layout: buildCashLayout() };
}

function commonAtmNumber(atms, key, fallback) {
  const values = [...new Set(atms.map((atm) => Number(atm[key])).filter((value) => Number.isFinite(value)))];
  return values.length === 1 ? values[0] : fallback;
}

function validateForm(form) {
  const errors = {};
  fields.forEach(([key, label, , minLength]) => {
    const value = form[key].trim();
    if (!value) {
      errors[key] = `${label}: هذا الحقل مطلوب.`;
    } else if (value.length < minLength) {
      errors[key] = `${label}: يجب أن يحتوي على ${minLength} أحرف على الأقل.`;
    }
  });
  return errors;
}

function getConfigStatus(atm) {
  if (hasActiveConfigError(atm)) return { label: "Failed", tone: "bg-rose-50 text-rose-700", icon: XCircle };
  if ((atm.applied_config_version || 0) < (atm.config_version || 0)) {
    return { label: "Pending", tone: "bg-amber-50 text-amber-700", icon: Clock3 };
  }
  return { label: "Synced", tone: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 };
}

function hasCurrentModuleError(atm) {
  return Object.values(atm.module_status_json || {}).some((status) => String(status).toLowerCase() === "error");
}

function hasRecentAgentError(atm) {
  if (!atm.last_agent_error_at) return false;
  const timestamp = new Date(atm.last_agent_error_at).getTime();
  if (!Number.isFinite(timestamp)) return false;
  return Date.now() - timestamp <= 10 * 60 * 1000;
}

function hasActiveConfigError(atm) {
  return Boolean(atm.last_config_error && Number(atm.applied_config_version || 0) < Number(atm.config_version || 0));
}

function hasActiveSwitchError(atm) {
  return Boolean(atm.last_switch_probe_error && String(atm.last_switch_probe_status || "").toLowerCase() === "failed");
}

function getActiveProblem(atm) {
  if (hasActiveConfigError(atm)) return atm.last_config_error;
  if (hasRecentAgentError(atm)) return atm.last_agent_error;
  if (hasCurrentModuleError(atm)) return atm.last_agent_error || "يوجد خطأ حالي في إحدى وحدات الـ Agent.";
  if (hasActiveSwitchError(atm)) return atm.last_switch_probe_error;
  return "";
}

function getAtmHealth(atm) {
  const online = isRecentlyOnline(atm);
  const hasError =
    hasActiveConfigError(atm) || hasRecentAgentError(atm) || hasCurrentModuleError(atm) || hasActiveSwitchError(atm);

  if (!online) {
    return {
      rank: 0,
      label: "offline",
      title: "غير متصل",
      tone: "bg-rose-50 text-rose-700",
      border: "border-rose-200",
      icon: WifiOff,
    };
  }
  if (hasError) {
    return {
      rank: 1,
      label: "error",
      title: "خطأ",
      tone: "bg-rose-50 text-rose-700",
      border: "border-rose-200",
      icon: ShieldAlert,
    };
  }
  if ((atm.applied_config_version || 0) < (atm.config_version || 0)) {
    return {
      rank: 2,
      label: "pending",
      title: "بانتظار Sync",
      tone: "bg-amber-50 text-amber-700",
      border: "border-amber-200",
      icon: Clock3,
    };
  }
  return {
    rank: 3,
    label: "online",
    title: "متصل",
    tone: "bg-emerald-50 text-emerald-700",
    border: "border-slate-200",
    icon: Wifi,
  };
}

function buildSettingsForm(atm) {
  return {
    name: atm?.name || "",
    media_path: atm?.media_path || "",
    backup_path: atm?.backup_path || "",
    temp_path: atm?.temp_path || "",
    check_interval_seconds: String(atm?.check_interval_seconds || 300),
    heartbeat_interval_seconds: String(atm?.heartbeat_interval_seconds || 60),
    config_sync_interval_seconds: String(atm?.config_sync_interval_seconds || 120),
    media_update_enabled: atm?.media_update_enabled ?? true,
    cash_monitoring_enabled: atm?.cash_monitoring_enabled ?? false,
    atm_cash_mode: atm?.atm_cash_mode || "DISPENSE_ONLY",
    cash_provider: normalizeCashProvider(atm?.cash_provider, atm?.cash_monitoring_enabled),
    xfs_profile: atm?.xfs_profile || "ncr_aptra",
    xfs_logical_service: atm?.xfs_logical_service || xfsProfileDefaults[atm?.xfs_profile] || "MediaDispenser1",
    xfs_msxfs_path: atm?.xfs_msxfs_path || "",
    xfs_version_range: atm?.xfs_version_range || "0x00031E03",
    cash_layout: normalizeCashLayout(atm?.cash_layout_json),
    cash_read_interval_seconds: String(atm?.cash_read_interval_seconds || 120),
    cash_stale_after_minutes: String(atm?.cash_stale_after_minutes || 10),
    switch_probe_host: atm?.switch_probe_host || "172.16.25.75",
    switch_probe_port: String(atm?.switch_probe_port || 10200),
  };
}

function isGrgProfile(value) {
  return String(value || "").toLowerCase() === "grg";
}

function buildInstallCommand(atmId, apiKey) {
  return `atm-agent.exe install --server-url="${apiBaseUrl}" --atm-id="${atmId}" --api-key="${apiKey}" --run-mode auto`;
}

function getLatencyTone(latencyMs) {
  if (!Number.isFinite(latencyMs)) return "bg-slate-100 text-slate-600";
  if (latencyMs <= 100) return "bg-emerald-50 text-emerald-700";
  if (latencyMs <= 300) return "bg-amber-50 text-amber-700";
  return "bg-rose-50 text-rose-700";
}

function formatLatency(latencyMs) {
  return Number.isFinite(latencyMs) ? `${latencyMs} ms` : "-";
}

function getAtmLatencyTone(atm) {
  if (!isRecentlyOnline(atm)) return "bg-slate-100 text-slate-500";
  return getLatencyTone(atm.latency_ms);
}

function formatAtmLatency(atm) {
  return isRecentlyOnline(atm) ? formatLatency(atm.latency_ms) : "-";
}

function getDiagnosticsTone(diagnostics) {
  if (!diagnostics) return "border-slate-200 bg-slate-50 text-slate-600";
  if (diagnostics.severity === "ok") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (diagnostics.severity === "warning") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-rose-200 bg-rose-50 text-rose-700";
}

function getSwitchProbeTone(status) {
  if (status === "success") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-rose-50 text-rose-700";
  if (status === "pending" || status === "running") return "bg-amber-50 text-amber-700";
  return "bg-slate-100 text-slate-600";
}

function formatSwitchProbe(atm) {
  if (!atm.last_switch_probe_status) return "لم يفحص";
  if (atm.last_switch_probe_status === "success") return `نجح ${atm.last_switch_probe_latency_ms ?? "-"} ms`;
  if (atm.last_switch_probe_status === "failed") return "فشل";
  return atm.last_switch_probe_status;
}

function formatSwitchProbeStatus(status) {
  if (status === "success") return "نجح";
  if (status === "failed") return "فشل";
  if (status === "running") return "قيد الفحص";
  if (status === "pending") return "بانتظار Agent";
  return status || "لم يفحص";
}

function isFinalSwitchProbe(status) {
  return status === "success" || status === "failed";
}

function formatSeconds(seconds) {
  if (typeof seconds !== "number") return "لا يوجد اتصال";
  if (seconds < 60) return `قبل ${seconds} ثانية`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `قبل ${minutes} دقيقة`;
  const hours = Math.floor(minutes / 60);
  return `قبل ${hours} ساعة`;
}

function getEventTone(severity) {
  if (severity === "error") {
    return {
      dot: "bg-rose-500",
      badge: "bg-rose-50 text-rose-700",
      border: "border-rose-100",
    };
  }
  if (severity === "warning") {
    return {
      dot: "bg-amber-500",
      badge: "bg-amber-50 text-amber-700",
      border: "border-amber-100",
    };
  }
  if (severity === "success") {
    return {
      dot: "bg-emerald-500",
      badge: "bg-emerald-50 text-emerald-700",
      border: "border-emerald-100",
    };
  }
  return {
    dot: "bg-slate-400",
    badge: "bg-slate-100 text-slate-600",
    border: "border-slate-100",
  };
}

function formatEventSource(source) {
  const labels = {
    agent: "Agent",
    audit: "Audit",
    cash: "Cash",
    command: "Command",
    config: "Config",
    media: "Media",
    notification: "Email",
    switch: "Switch",
  };
  return labels[source] || source || "-";
}

function formatEventDate(event) {
  return event?.source === "journal" ? formatLocalWallDate(event.occurred_at) : formatApiDate(event?.occurred_at);
}

function formatEventStatus(status) {
  const labels = {
    acknowledged: "تم الاستلام",
    applied: "مطبق",
    closed: "مغلق",
    completed: "مكتمل",
    failed: "فشل",
    ok: "OK",
    offline: "غير متصل",
    online: "متصل",
    open: "مفتوح",
    pending: "بانتظار",
    received: "وصلت",
    running: "قيد التنفيذ",
    sent: "مرسل",
    success: "نجح",
    synced: "Synced",
    warning: "تنبيه",
  };
  return labels[status] || status || "";
}

function compactEventDetails(details) {
  if (!details || typeof details !== "object") return [];
  return Object.entries(details)
    .filter(([, value]) => value !== null && value !== undefined && value !== "" && typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`);
}

function getXfsProfileLabel(value) {
  if (value === "grg") return "GRG";
  if (value === "custom") return "Custom";
  return "NCR";
}

function getModuleStatus(atm, moduleName) {
  return (atm.module_status_json && atm.module_status_json[moduleName]) || "-";
}

function isSwitchTargetDirty(atm, form) {
  if (!atm) return false;
  return (
    String(form.switch_probe_host || "").trim() !== String(atm.switch_probe_host || "") ||
    String(form.switch_probe_port || "") !== String(atm.switch_probe_port || "")
  );
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const element = document.createElement("textarea");
  element.value = text;
  element.style.position = "fixed";
  element.style.opacity = "0";
  document.body.appendChild(element);
  element.select();
  document.execCommand("copy");
  document.body.removeChild(element);
}

function wait(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function MetricCard({ label, value, tone = "slate", icon: Icon }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    teal: "border-teal-200 bg-teal-50 text-teal-900",
  };

  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-slate-600">{label}</div>
        {Icon && <Icon size={18} className="opacity-75" />}
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none sm:text-3xl">{value}</div>
    </div>
  );
}

function ToggleBox({ label, checked, onChange }) {
  return (
    <label className="flex min-h-12 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="h-4 w-4" />
    </label>
  );
}

function SettingsGroup({ title, icon: Icon, meta, defaultOpen = false, children }) {
  const openProps = defaultOpen ? { open: true } : {};
  return (
    <details {...openProps} className="group rounded-lg border border-slate-200 bg-white shadow-sm">
      <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-4 py-3 [&::-webkit-details-marker]:hidden">
        <div className="flex min-w-0 items-center gap-2">
          {Icon && <Icon size={18} className="shrink-0 text-slate-500" />}
          <span className="truncate font-semibold text-slate-950">{title}</span>
          {meta && <span className="truncate text-sm text-slate-500">{meta}</span>}
        </div>
        <ChevronDown size={18} className="shrink-0 text-slate-400 transition group-open:rotate-180" />
      </summary>
      <div className="border-t border-slate-100 p-4">{children}</div>
    </details>
  );
}

function AtmEventTimeline({ events, loading, onRefresh }) {
  const visibleEvents = Array.isArray(events) ? events.slice(0, 80) : [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-500">سجل موحد لآخر اتصال، النقد، الأوامر، التحديثات، البريد والتغييرات.</div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
          title="تحديث سجل الأحداث"
        >
          <RefreshCw size={15} />
          <span>{loading ? "جار التحديث" : "تحديث"}</span>
        </button>
      </div>

      {loading && (
        <div className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">
          جار تحميل سجل الأحداث...
        </div>
      )}

      {!loading && visibleEvents.length === 0 && (
        <div className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">
          لا توجد أحداث لهذا الصراف بعد.
        </div>
      )}

      {!loading && visibleEvents.length > 0 && (
        <div className="max-h-96 overflow-y-auto rounded-lg border border-slate-200 bg-white">
          <div className="divide-y divide-slate-100">
            {visibleEvents.map((event) => {
              const tone = getEventTone(event.severity);
              const details = compactEventDetails(event.details);
              const statusLabel = formatEventStatus(event.status);

              return (
                <article key={event.id} className={`grid gap-3 px-3 py-3 sm:grid-cols-[auto_1fr_auto] ${tone.border}`}>
                  <span className={`mt-2 h-2.5 w-2.5 rounded-full ${tone.dot}`} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="truncate text-sm font-semibold text-slate-950">{event.title}</div>
                      {statusLabel && (
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone.badge}`}>{statusLabel}</span>
                      )}
                    </div>
                    {event.message && <div className="mt-1 break-words text-sm text-slate-600">{event.message}</div>}
                    {details.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {details.map((item) => (
                          <span key={item} className="rounded-full bg-slate-50 px-2 py-0.5 text-xs text-slate-500" dir="ltr">
                            {item}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-slate-500 sm:text-left">
                    <div>{formatEventDate(event)}</div>
                    <div className="mt-1 font-medium text-slate-600">{formatEventSource(event.source)}</div>
                    {event.actor && <div className="mt-1 truncate" title={event.actor}>{event.actor}</div>}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function AgentInstallHint({ atm }) {
  const grg = isGrgProfile(atm?.xfs_profile);
  return (
    <div
      className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
        grg ? "border-amber-200 bg-amber-50 text-amber-900" : "border-slate-200 bg-slate-50 text-slate-600"
      }`}
    >
      <div className="font-semibold text-slate-950">تعليمات تثبيت الـ Agent</div>
      <div className="mt-1">
        {grg
          ? "هذا الصراف GRG. عند استخدام نسخة Agent الجديدة مع --run-mode auto سيقوم التثبيت تلقائياً بتشغيله كمهمة مجدولة مخفية بدلاً من Windows Service."
          : "هذا الصراف ليس GRG. سيستخدم التثبيت التلقائي Windows Service كالمعتاد."}
      </div>
      {grg && (
        <div className="mt-1">
          شغّل أمر التثبيت من مستخدم Windows الذي يفتح XFS بنجاح، مثل Administrator، أو استخدم خيار
          <span className="mx-1 font-mono" dir="ltr">
            --task-user
          </span>
          عند الحاجة.
        </div>
      )}
    </div>
  );
}

function CassetteLayoutEditor({ layout, onChange, title = "تخطيط الكاسيتات", fieldError }) {
  const normalized = normalizeCashLayout(layout);
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="text-sm font-semibold text-slate-950">{title}</div>
      </div>
      <div className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-4">
        {normalized.map((item) => {
          const defaults = currencyDefaults[item.currency] || currencyDefaults.YER;
          return (
            <label key={item.cassette_no} className="block rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
              <span className="mb-1 block text-sm font-medium text-slate-700">Cassette {item.cassette_no}</span>
              <select
                className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                value={item.currency}
                onChange={(event) => onChange(updateCashLayoutCurrency(normalized, item.cassette_no, event.target.value))}
              >
                {currencyOptions.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                <span className="rounded-full bg-white px-2 py-1">{item.currency}</span>
                <span className="rounded-full bg-white px-2 py-1">{defaults.denomination}</span>
              </div>
            </label>
          );
        })}
      </div>
      {fieldError && <div className="border-t border-rose-100 px-3 py-2 text-xs text-rose-700">{fieldError}</div>}
    </div>
  );
}

function AtmCard({ atm, onOpenSettings, onDelete, onProbeSwitch, switchProbeBusyId, deletingAtmId }) {
  const health = getAtmHealth(atm);
  const HealthIcon = health.icon;
  const configStatus = getConfigStatus(atm);
  const ConfigIcon = configStatus.icon;
  const lastProblem = getActiveProblem(atm);

  return (
    <article className={`rounded-lg border bg-white p-4 shadow-sm ${health.border}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-lg font-semibold text-slate-950">{atm.name}</span>
            <span className="rounded-full bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">{atm.atm_id}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500">
            <span>{atm.branch || "-"}</span>
            <span dir="ltr">{atm.vpn_ip}</span>
          </div>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${health.tone}`}>
          <HealthIcon size={16} />
          {health.title}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-xs text-slate-500">آخر اتصال</div>
          <div className="mt-1 font-semibold text-slate-950">{formatLastSeenAge(atm)}</div>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-xs text-slate-500">Latency</div>
          <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${getAtmLatencyTone(atm)}`} dir="ltr">
            {formatAtmLatency(atm)}
          </span>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-xs text-slate-500">Agent</div>
          <div className="mt-1 truncate font-semibold text-slate-950">{atm.agent_version || "-"}</div>
        </div>
        <div className="rounded-lg bg-slate-50 px-3 py-2">
          <div className="text-xs text-slate-500">XFS</div>
          <div className="mt-1 font-semibold text-slate-950">{getXfsProfileLabel(atm.xfs_profile)}</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className={`inline-flex min-h-8 items-center gap-1 rounded-full px-3 text-xs font-semibold ${configStatus.tone}`}>
          <ConfigIcon size={14} />
          Config: {configStatus.label}
        </span>
        <span className={`inline-flex min-h-8 items-center rounded-full px-3 text-xs font-semibold ${getSwitchProbeTone(atm.last_switch_probe_status)}`}>
          Switch: {formatSwitchProbe(atm)}
        </span>
        <span className="inline-flex min-h-8 items-center rounded-full bg-slate-100 px-3 text-xs font-semibold text-slate-700">
          Media: {getModuleStatus(atm, "media_update")}
        </span>
        <span className="inline-flex min-h-8 items-center rounded-full bg-slate-100 px-3 text-xs font-semibold text-slate-700">
          Cash: {getModuleStatus(atm, "cash_monitoring")}
        </span>
      </div>

      {lastProblem && (
        <div className="mt-3 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700">
          <div className="truncate" title={lastProblem}>
            {lastProblem}
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <button
          onClick={() => onOpenSettings(atm)}
          className="focus-ring inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
          title="إعدادات الصراف"
        >
          <Settings2 size={16} />
          <span>إعدادات</span>
        </button>
        <button
          onClick={() => onProbeSwitch(atm)}
          disabled={switchProbeBusyId === atm.atm_id}
          className="focus-ring inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          title={`فحص TCP من الصراف إلى ${atm.switch_probe_host}:${atm.switch_probe_port}`}
        >
          <Network size={16} />
          <span>{switchProbeBusyId === atm.atm_id ? "جار" : "فحص"}</span>
        </button>
        <button
          onClick={() => onDelete(atm)}
          disabled={deletingAtmId === atm.atm_id}
          className="focus-ring inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-60"
          title="حذف الصراف"
        >
          <Trash2 size={16} />
          <span>{deletingAtmId === atm.atm_id ? "جار" : "حذف"}</span>
        </button>
      </div>
    </article>
  );
}

export default function Atms({ atms, onChanged }) {
  const [form, setForm] = useState(() => buildEmptyForm());
  const [selectedAtmId, setSelectedAtmId] = useState("");
  const [settingsForm, setSettingsForm] = useState({});
  const [settingsMessage, setSettingsMessage] = useState("");
  const [generatedKey, setGeneratedKey] = useState("");
  const [generatedKeyAtmId, setGeneratedKeyAtmId] = useState("");
  const [generatedKeyAtm, setGeneratedKeyAtm] = useState(null);
  const [copyMessage, setCopyMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [regeneratingKey, setRegeneratingKey] = useState(false);
  const [deletingAtmId, setDeletingAtmId] = useState("");
  const [diagnostics, setDiagnostics] = useState(null);
  const [loadingDiagnostics, setLoadingDiagnostics] = useState(false);
  const [atmEvents, setAtmEvents] = useState([]);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [switchProbeBusyId, setSwitchProbeBusyId] = useState("");
  const [switchProbeDialog, setSwitchProbeDialog] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const selectedAtm = useMemo(
    () => atms.find((atm) => atm.atm_id === selectedAtmId) || null,
    [atms, selectedAtmId],
  );

  const metrics = useMemo(() => {
    const online = atms.filter(isRecentlyOnline).length;
    const pendingConfig = atms.filter((atm) => (atm.applied_config_version || 0) < (atm.config_version || 0)).length;
    const errors = atms.filter((atm) => getAtmHealth(atm).label === "error").length;
    return {
      total: atms.length,
      online,
      offline: atms.length - online,
      pendingConfig,
      errors,
    };
  }, [atms]);

  const filteredAtms = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...atms]
      .filter((atm) => {
        const health = getAtmHealth(atm);
        if (statusFilter === "online" && !isRecentlyOnline(atm)) return false;
        if (statusFilter === "offline" && isRecentlyOnline(atm)) return false;
        if (statusFilter === "pending" && (atm.applied_config_version || 0) >= (atm.config_version || 0)) return false;
        if (statusFilter === "error" && health.label !== "error") return false;
        if (!needle) return true;
        return [atm.atm_id, atm.name, atm.branch, atm.vpn_ip]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(needle));
      })
      .sort((first, second) => {
        const firstHealth = getAtmHealth(first);
        const secondHealth = getAtmHealth(second);
        if (firstHealth.rank !== secondHealth.rank) return firstHealth.rank - secondHealth.rank;
        return String(first.atm_id).localeCompare(String(second.atm_id), "ar");
      });
  }, [atms, query, statusFilter]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setGeneratedKey("");
    setGeneratedKeyAtmId("");
    setGeneratedKeyAtm(null);
    setCopyMessage("");

    const localErrors = validateForm(form);
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      setError("يرجى تصحيح الحقول المحددة.");
      return;
    }

    setLoading(true);
    try {
      const intervalDefaults = {
        config_sync_interval_seconds: commonAtmNumber(atms, "config_sync_interval_seconds", 120),
        cash_read_interval_seconds: commonAtmNumber(atms, "cash_read_interval_seconds", 120),
        cash_stale_after_minutes: commonAtmNumber(atms, "cash_stale_after_minutes", 10),
      };
      const result = await api.createAtm({
        atm_id: form.atm_id.trim(),
        name: form.name.trim(),
        vpn_ip: form.vpn_ip.trim(),
        branch: form.branch.trim(),
        xfs_profile: form.xfs_profile || "ncr_aptra",
        xfs_logical_service: xfsProfileDefaults[form.xfs_profile] || "MediaDispenser1",
        atm_cash_mode: "DISPENSE_ONLY",
        cash_provider: "xfs_cdm",
        ...intervalDefaults,
        cash_layout: normalizeCashLayout(form.cash_layout),
      });
      setGeneratedKey(result.api_key);
      setGeneratedKeyAtmId(result.atm.atm_id);
      setGeneratedKeyAtm(result.atm);
      setForm(buildEmptyForm());
      setShowCreateForm(false);
      setSelectedAtmId(result.atm.atm_id);
      setSettingsForm(buildSettingsForm(result.atm));
      onChanged();
    } catch (err) {
      setFieldErrors(err.fieldErrors || {});
      setError(err.message || "تعذر إنشاء الصراف");
    } finally {
      setLoading(false);
    }
  }

  function openSettings(atm) {
    setSelectedAtmId(atm.atm_id);
    setSettingsForm(buildSettingsForm(atm));
    setSettingsMessage("");
    setCopyMessage("");
    setFieldErrors({});
    setError("");
    setDiagnostics(null);
    setAtmEvents([]);
    loadEvents(atm.atm_id);
  }

  function closeSettings() {
    setSelectedAtmId("");
    setSettingsForm({});
    setDiagnostics(null);
    setAtmEvents([]);
    setSettingsMessage("");
    setCopyMessage("");
    setFieldErrors({});
  }

  async function loadDiagnostics(atmId = selectedAtm?.atm_id) {
    if (!atmId) return;
    setLoadingDiagnostics(true);
    try {
      setDiagnostics(await api.getAtmDiagnostics(atmId));
    } catch (err) {
      setDiagnostics(null);
      setError(err.message || "تعذر تحميل تشخيص الـ Agent");
    } finally {
      setLoadingDiagnostics(false);
    }
  }

  async function loadEvents(atmId = selectedAtm?.atm_id) {
    if (!atmId) return;
    setLoadingEvents(true);
    try {
      const events = await api.getAtmEvents(atmId, 80);
      setAtmEvents(Array.isArray(events) ? events : []);
    } catch (err) {
      setAtmEvents([]);
      setError(err.message || "تعذر تحميل سجل أحداث الصراف");
    } finally {
      setLoadingEvents(false);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    if (!selectedAtm) return;

    setSettingsMessage("");
    setError("");
    setFieldErrors({});

    const trimmedName = (settingsForm.name || "").trim();
    if (trimmedName.length < 2) {
      setFieldErrors({ name: "اسم الصراف يجب أن يحتوي على حرفين على الأقل." });
      setError("يرجى تصحيح الحقول المحددة.");
      return;
    }

    setSavingSettings(true);
    try {
      const payload = {
        name: trimmedName,
        media_path: settingsForm.media_path.trim(),
        backup_path: settingsForm.backup_path.trim(),
        temp_path: settingsForm.temp_path.trim(),
        check_interval_seconds: Number(settingsForm.check_interval_seconds),
        heartbeat_interval_seconds: Number(settingsForm.heartbeat_interval_seconds),
        config_sync_interval_seconds: Number(settingsForm.config_sync_interval_seconds),
        switch_probe_host: settingsForm.switch_probe_host.trim(),
        switch_probe_port: Number(settingsForm.switch_probe_port),
        media_update_enabled: Boolean(settingsForm.media_update_enabled),
        cash_monitoring_enabled: Boolean(settingsForm.cash_monitoring_enabled),
        atm_cash_mode: "DISPENSE_ONLY",
        cash_provider: normalizeCashProvider(settingsForm.cash_provider, settingsForm.cash_monitoring_enabled),
        xfs_profile: settingsForm.xfs_profile || "ncr_aptra",
        xfs_logical_service: (settingsForm.xfs_logical_service || "").trim() || "MediaDispenser1",
        xfs_msxfs_path: (settingsForm.xfs_msxfs_path || "").trim() || null,
        xfs_version_range: (settingsForm.xfs_version_range || "").trim() || "0x00031E03",
        cash_layout: normalizeCashLayout(settingsForm.cash_layout),
        cash_read_interval_seconds: Number(settingsForm.cash_read_interval_seconds),
        cash_stale_after_minutes: Number(settingsForm.cash_stale_after_minutes),
      };
      const updated = await api.updateAtm(selectedAtm.atm_id, payload);
      setSettingsForm(buildSettingsForm(updated));
      const configVersionChanged = Number(updated.config_version) !== Number(selectedAtm.config_version);
      setSettingsMessage(
        configVersionChanged ? `تم الحفظ. Config Version الآن ${updated.config_version}.` : "تم حفظ بيانات الصراف.",
      );
      await onChanged();
    } catch (err) {
      setFieldErrors(err.fieldErrors || {});
      setError(err.message || "تعذر حفظ إعدادات الصراف");
    } finally {
      setSavingSettings(false);
    }
  }

  async function deleteAtm(atm) {
    const activeText =
      atm.active_update_count > 0 ? `\n\nتنبيه: يوجد ${atm.active_update_count} تحديث نشط مرتبط بهذا الصراف.` : "";
    const confirmed = window.confirm(
      `هل تريد حذف الصراف ${atm.atm_id}؟\nسيتم حذف تعيينات التحديث والسجلات المرتبطة به من لوحة التحكم.${activeText}`,
    );
    if (!confirmed) return;

    setDeletingAtmId(atm.atm_id);
    setError("");
    setFieldErrors({});
    setSettingsMessage("");

    try {
      await api.deleteAtm(atm.atm_id);
      if (selectedAtmId === atm.atm_id) closeSettings();
      onChanged();
    } catch (err) {
      if (err.status === 409 && err.payload?.detail?.active_update_count) {
        const force = window.confirm(
          `يوجد ${err.payload.detail.active_update_count} تحديث نشط لهذا الصراف.\nهل تريد الحذف بالقوة؟`,
        );
        if (force) {
          try {
            await api.deleteAtm(atm.atm_id, true);
            if (selectedAtmId === atm.atm_id) closeSettings();
            onChanged();
            return;
          } catch (forceErr) {
            setError(forceErr.message || "تعذر حذف الصراف");
          }
        }
        return;
      }
      setError(err.message || "تعذر حذف الصراف");
    } finally {
      setDeletingAtmId("");
    }
  }

  async function regenerateApiKey() {
    if (!selectedAtm) return;
    const confirmed = window.confirm(
      `هل تريد توليد API Key جديد للصراف ${selectedAtm.atm_id}؟\nالمفتاح القديم سيتوقف، ويجب إعادة تثبيت أو تحديث خدمة الـ Agent على الصراف.`,
    );
    if (!confirmed) return;

    setRegeneratingKey(true);
    setSettingsMessage("");
    setCopyMessage("");
    setError("");

    try {
      const result = await api.regenerateAtmApiKey(selectedAtm.atm_id);
      setGeneratedKey(result.api_key);
      setGeneratedKeyAtmId(result.atm.atm_id);
      setGeneratedKeyAtm(result.atm);
      setSettingsMessage("تم توليد API Key جديد. انسخ أمر التثبيت الآن؛ لن يظهر المفتاح مرة أخرى.");
      onChanged();
    } catch (err) {
      setError(err.message || "تعذر توليد API Key جديد");
    } finally {
      setRegeneratingKey(false);
    }
  }

  async function requestSwitchProbe(atm, target = null) {
    setSwitchProbeBusyId(atm.atm_id);
    setError("");
    setSettingsMessage("");
    try {
      const probe = await api.requestSwitchProbe(atm.atm_id, target);
      setSwitchProbeDialog({
        open: true,
        atm: { atm_id: atm.atm_id, name: atm.name },
        probe,
        error: "",
        refreshing: false,
      });
      await pollSwitchProbeResult(atm, probe);
    } catch (err) {
      setError(err.message || "تعذر إرسال طلب فحص السويتش");
      setSwitchProbeDialog({
        open: true,
        atm: { atm_id: atm.atm_id, name: atm.name },
        probe: {
          host: atm.switch_probe_host,
          port: atm.switch_probe_port,
          status: "failed",
          error_message: err.message || "تعذر إرسال طلب فحص السويتش",
        },
        error: err.message || "تعذر إرسال طلب فحص السويتش",
        refreshing: false,
      });
    } finally {
      setSwitchProbeBusyId("");
    }
  }

  async function pollSwitchProbeResult(atm, initialProbe) {
    let latest = initialProbe;
    for (let attempt = 0; attempt < 18 && !isFinalSwitchProbe(latest.status); attempt += 1) {
      await wait(attempt === 0 ? 1000 : 2000);
      try {
        const probes = await api.listSwitchProbes(atm.atm_id);
        latest = probes.find((item) => item.id === initialProbe.id) || latest;
        setSwitchProbeDialog((current) => {
          if (!current?.open || current.probe?.id !== initialProbe.id) return current;
          return { ...current, probe: latest, error: "" };
        });
        if (isFinalSwitchProbe(latest.status)) {
          onChanged();
          return;
        }
      } catch (err) {
        setSwitchProbeDialog((current) => {
          if (!current?.open || current.probe?.id !== initialProbe.id) return current;
          return { ...current, error: err.message || "تعذر تحديث نتيجة الفحص" };
        });
        return;
      }
    }
    onChanged();
  }

  async function refreshSwitchProbeDialog() {
    const current = switchProbeDialog;
    if (!current?.atm?.atm_id || !current?.probe?.id) return;
    setSwitchProbeDialog((value) => (value ? { ...value, refreshing: true, error: "" } : value));
    try {
      const probes = await api.listSwitchProbes(current.atm.atm_id);
      const latest = probes.find((item) => item.id === current.probe.id) || current.probe;
      setSwitchProbeDialog((value) => (value ? { ...value, probe: latest, refreshing: false, error: "" } : value));
      onChanged();
    } catch (err) {
      setSwitchProbeDialog((value) =>
        value ? { ...value, refreshing: false, error: err.message || "تعذر تحديث نتيجة الفحص" } : value,
      );
    }
  }

  async function copyInstallCommand() {
    if (!generatedKey || !generatedKeyAtmId) return;
    try {
      await copyText(buildInstallCommand(generatedKeyAtmId, generatedKey));
      setCopyMessage("تم نسخ أمر التثبيت.");
    } catch {
      setCopyMessage("تعذر النسخ تلقائياً. انسخ الأمر يدوياً.");
    }
  }

  async function copyApiKey() {
    if (!generatedKey) return;
    try {
      await copyText(generatedKey);
      setCopyMessage("تم نسخ API Key.");
    } catch {
      setCopyMessage("تعذر النسخ تلقائياً. انسخ المفتاح يدوياً.");
    }
  }

  const installCommand = generatedKey && generatedKeyAtmId ? buildInstallCommand(generatedKeyAtmId, generatedKey) : "";

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">إدارة الصرافات</h1>
        </div>
        <button
          onClick={() => setShowCreateForm((current) => !current)}
          className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
          title="إضافة صراف"
        >
          <Plus size={18} />
          <span>إضافة صراف</span>
        </button>
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="الصرافات" value={metrics.total} icon={Server} />
        <MetricCard label="Online" value={metrics.online} tone="emerald" icon={Wifi} />
        <MetricCard label="Offline" value={metrics.offline} tone={metrics.offline ? "rose" : "emerald"} icon={WifiOff} />
        <MetricCard label="Pending Config" value={metrics.pendingConfig} tone={metrics.pendingConfig ? "amber" : "emerald"} icon={Clock3} />
        <MetricCard label="Errors" value={metrics.errors} tone={metrics.errors ? "rose" : "emerald"} icon={ShieldAlert} />
      </div>

      {(showCreateForm || generatedKey) && (
        <div className="mb-5 rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div className="flex items-center gap-2 font-semibold text-slate-950">
              <Plus size={18} />
              <span>صراف جديد</span>
            </div>
            <button
              type="button"
              onClick={() => setShowCreateForm(false)}
              className="focus-ring rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              title="إغلاق"
            >
              <XCircle size={18} />
            </button>
          </div>

          {showCreateForm && (
            <form noValidate onSubmit={submit} className="p-4">
              <div className="grid gap-3 md:grid-cols-4">
                {fields.map(([key, label, placeholder, minLength]) => (
                  <label key={key} className="block">
                    <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
                    <input
                      className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                        fieldErrors[key] ? "border-rose-400 bg-rose-50" : "border-slate-300"
                      }`}
                      value={form[key]}
                      onChange={(event) => {
                        setForm((current) => ({ ...current, [key]: event.target.value }));
                        setFieldErrors((current) => {
                          if (!current[key]) return current;
                          const next = { ...current };
                          delete next[key];
                          return next;
                        });
                      }}
                      minLength={minLength}
                      placeholder={placeholder}
                      aria-invalid={Boolean(fieldErrors[key])}
                      required
                    />
                    {fieldErrors[key] && <span className="mt-1 block text-xs text-rose-700">{fieldErrors[key]}</span>}
                  </label>
                ))}
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">نوع XFS</span>
                  <select
                    className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                    value={form.xfs_profile}
                    onChange={(event) => setForm((current) => ({ ...current, xfs_profile: event.target.value }))}
                  >
                    <option value="ncr_aptra">NCR</option>
                    <option value="grg">GRG</option>
                  </select>
                </label>
              </div>
              {isGrgProfile(form.xfs_profile) && (
                <AgentInstallHint atm={{ xfs_profile: form.xfs_profile }} />
              )}
              <div className="mt-4">
                <CassetteLayoutEditor
                  layout={form.cash_layout}
                  onChange={(nextLayout) => setForm((current) => ({ ...current, cash_layout: nextLayout }))}
                  title="عملة الكاسيتات"
                  fieldError={fieldErrors.cash_layout}
                />
              </div>
              <button
                disabled={loading}
                className="focus-ring mt-4 inline-flex min-h-11 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                title="إضافة صراف"
              >
                <Plus size={17} />
                <span>{loading ? "جار الإضافة..." : "إضافة صراف"}</span>
              </button>
            </form>
          )}

          {generatedKey && (
            <div className="border-t border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="font-medium">API Key جديد للصراف {generatedKeyAtmId}</div>
              <div className="mt-2 overflow-x-auto rounded border border-amber-200 bg-white px-2 py-1 font-mono text-xs" dir="ltr">
                {generatedKey}
              </div>
              <div className="mt-2 overflow-x-auto rounded border border-amber-200 bg-white px-2 py-1 font-mono text-xs" dir="ltr">
                {installCommand}
              </div>
              <AgentInstallHint atm={generatedKeyAtm} />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={copyApiKey}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs text-amber-900 hover:bg-amber-100"
                  title="نسخ API Key"
                >
                  <KeyRound size={14} />
                  <span>نسخ API Key</span>
                </button>
                <button
                  type="button"
                  onClick={copyInstallCommand}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs text-amber-900 hover:bg-amber-100"
                  title="نسخ أمر التثبيت"
                >
                  <Clipboard size={14} />
                  <span>Copy Install Command</span>
                </button>
              </div>
              {copyMessage && <div className="mt-2 text-xs">{copyMessage}</div>}
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 shrink-0" size={17} />
          <div>
            <div className="font-medium">{error}</div>
            {Object.values(fieldErrors).length > 0 && (
              <ul className="mt-1 space-y-1">
                {Object.values(fieldErrors).map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <div className="mb-5 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pr-10 pl-3 text-sm"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="بحث بالاسم أو ATM ID أو الفرع أو IP"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal size={18} className="text-slate-500" />
            {[
              ["all", "الكل"],
              ["online", "Online"],
              ["offline", "Offline"],
              ["pending", "Pending Config"],
              ["error", "Errors"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatusFilter(value)}
                className={`focus-ring min-h-10 rounded-lg border px-3 text-sm ${
                  statusFilter === value
                    ? "border-teal-600 bg-teal-50 text-teal-800"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {filteredAtms.map((atm) => (
          <AtmCard
            key={atm.atm_id}
            atm={atm}
            onOpenSettings={openSettings}
            onDelete={deleteAtm}
            onProbeSwitch={requestSwitchProbe}
            switchProbeBusyId={switchProbeBusyId}
            deletingAtmId={deletingAtmId}
          />
        ))}
      </div>

      {filteredAtms.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500 shadow-sm">
          لا توجد صرافات مطابقة
        </div>
      )}

      {selectedAtm && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-slate-950/40"
          role="dialog"
          aria-modal="true"
          onClick={closeSettings}
        >
          <form
            noValidate
            onSubmit={saveSettings}
            className="flex h-full w-full max-w-4xl flex-col bg-white shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-semibold text-slate-950">{selectedAtm.name}</h2>
                  <span className="rounded-full bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">{selectedAtm.atm_id}</span>
                </div>
                <div className="mt-1 text-sm text-slate-500">
                  {selectedAtm.branch} · {selectedAtm.vpn_ip} · Agent {selectedAtm.agent_version || "-"}
                </div>
              </div>
              <button
                type="button"
                onClick={closeSettings}
                className="focus-ring rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                title="إغلاق"
              >
                <XCircle size={20} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div className="mb-4 grid gap-3 md:grid-cols-4">
                {(() => {
                  const status = getConfigStatus(selectedAtm);
                  const Icon = status.icon;
                  return (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                      <div className="text-slate-500">Config Sync</div>
                      <span className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs ${status.tone}`}>
                        <Icon size={14} />
                        {status.label}
                      </span>
                    </div>
                  );
                })()}
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <div className="text-slate-500">آخر اتصال</div>
                  <div className="mt-1 font-semibold text-slate-950">{formatLastSeenAge(selectedAtm)}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <div className="text-slate-500">Latency</div>
                  <span className={`mt-1 inline-flex rounded-full px-2 py-1 text-xs ${getAtmLatencyTone(selectedAtm)}`} dir="ltr">
                    {formatAtmLatency(selectedAtm)}
                  </span>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <div className="text-slate-500">Switch</div>
                  <span className={`mt-1 inline-flex rounded-full px-2 py-1 text-xs ${getSwitchProbeTone(selectedAtm.last_switch_probe_status)}`}>
                    {formatSwitchProbe(selectedAtm)}
                  </span>
                </div>
              </div>

              <section className="mb-4 rounded-lg border border-slate-200 bg-white">
                <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950">
                  بيانات الصراف
                </div>
                <div className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
                  <label className="block">
                    <span className="mb-1 block text-sm font-medium text-slate-700">اسم الصراف</span>
                    <input
                      className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                        fieldErrors.name ? "border-rose-400 bg-rose-50" : "border-slate-300 bg-white"
                      }`}
                      value={settingsForm.name || ""}
                      onChange={(event) => {
                        setSettingsForm((current) => ({ ...current, name: event.target.value }));
                        setFieldErrors((current) => {
                          if (!current.name) return current;
                          const next = { ...current };
                          delete next.name;
                          return next;
                        });
                      }}
                      minLength={2}
                      placeholder={selectedAtm.name}
                      required
                    />
                    {fieldErrors.name && <span className="mt-1 block text-xs text-rose-700">{fieldErrors.name}</span>}
                  </label>
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm md:min-w-36">
                    <div className="text-slate-500">ATM ID</div>
                    <div className="mt-1 font-mono font-semibold text-slate-950">{selectedAtm.atm_id}</div>
                  </div>
                </div>
              </section>

              <div className="grid gap-4 xl:grid-cols-2">
                <section className="rounded-lg border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950">
                    التشغيل والنقد
                  </div>
                  <div className="grid gap-3 p-4 sm:grid-cols-2">
                    <ToggleBox
                      label="تحديث الوسائط"
                      checked={Boolean(settingsForm.media_update_enabled)}
                      onChange={(value) => setSettingsForm((current) => ({ ...current, media_update_enabled: value }))}
                    />
                    <ToggleBox
                      label="مراقبة النقد"
                      checked={Boolean(settingsForm.cash_monitoring_enabled)}
                      onChange={(value) => setSettingsForm((current) => ({ ...current, cash_monitoring_enabled: value }))}
                    />
                    <label className="block">
                      <span className="mb-1 block text-sm font-medium text-slate-700">مزود النقد</span>
                      <select
                        className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                        value={normalizeCashProvider(settingsForm.cash_provider, settingsForm.cash_monitoring_enabled)}
                        onChange={(event) => setSettingsForm((current) => ({ ...current, cash_provider: event.target.value }))}
                      >
                        <option value="xfs_cdm">XFS CDM Provider</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm font-medium text-slate-700">نوع XFS</span>
                      <select
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.xfs_profile ? "border-rose-400 bg-rose-50" : "border-slate-300"
                        }`}
                        value={settingsForm.xfs_profile || "ncr_aptra"}
                        onChange={(event) => {
                          const nextProfile = event.target.value;
                          setSettingsForm((current) => ({
                            ...current,
                            xfs_profile: nextProfile,
                            xfs_logical_service: xfsProfileDefaults[nextProfile] || current.xfs_logical_service,
                            xfs_msxfs_path: current.xfs_msxfs_path || xfsMsxfsPathDefaults[nextProfile] || "",
                            cash_provider: nextProfile === "custom" ? normalizeCashProvider(current.cash_provider, current.cash_monitoring_enabled) : "xfs_cdm",
                          }));
                        }}
                      >
                        <option value="ncr_aptra">NCR APTRA</option>
                        <option value="grg">GRG</option>
                        <option value="custom">Custom</option>
                      </select>
                      {fieldErrors.xfs_profile && <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_profile}</span>}
                    </label>
                    <label className="block sm:col-span-2">
                      <span className="mb-1 block text-sm font-medium text-slate-700">اسم خدمة XFS</span>
                      <input
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.xfs_logical_service ? "border-rose-400 bg-rose-50" : "border-slate-300"
                        }`}
                        dir="ltr"
                        value={settingsForm.xfs_logical_service || ""}
                        onChange={(event) =>
                          setSettingsForm((current) => ({ ...current, xfs_logical_service: event.target.value }))
                        }
                        placeholder="MediaDispenser1 أو CDM"
                      />
                      {fieldErrors.xfs_logical_service && (
                        <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_logical_service}</span>
                      )}
                    </label>
                    <details className="group sm:col-span-2 rounded-lg border border-slate-200 bg-white">
                      <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm font-semibold text-slate-700 [&::-webkit-details-marker]:hidden">
                        <span>إعدادات XFS المتقدمة</span>
                        <ChevronDown size={16} className="text-slate-400 transition group-open:rotate-180" />
                      </summary>
                      <div className="grid gap-3 border-t border-slate-100 p-3 sm:grid-cols-2">
                    <label className="block sm:col-span-2">
                      <span className="mb-1 block text-sm font-medium text-slate-700">XFS msxfs.dll Path</span>
                      <input
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.xfs_msxfs_path ? "border-rose-400 bg-rose-50" : "border-slate-300"
                        }`}
                        dir="ltr"
                        value={settingsForm.xfs_msxfs_path || ""}
                        onChange={(event) =>
                          setSettingsForm((current) => ({ ...current, xfs_msxfs_path: event.target.value }))
                        }
                        placeholder="C:\\Windows\\SysWOW64\\msxfs.dll"
                      />
                      {fieldErrors.xfs_msxfs_path && (
                        <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_msxfs_path}</span>
                      )}
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm font-medium text-slate-700">XFS Version Range</span>
                      <input
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.xfs_version_range ? "border-rose-400 bg-rose-50" : "border-slate-300"
                        }`}
                        dir="ltr"
                        value={settingsForm.xfs_version_range || ""}
                        onChange={(event) =>
                          setSettingsForm((current) => ({ ...current, xfs_version_range: event.target.value }))
                        }
                        placeholder="0x00031E03"
                      />
                      {fieldErrors.xfs_version_range && (
                        <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_version_range}</span>
                      )}
                    </label>
                      </div>
                    </details>
                  </div>
                </section>

                <section className="rounded-lg border border-slate-200 bg-white">
                  <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="font-semibold text-slate-950">فحص السويتش</div>
                    <button
                      type="button"
                      onClick={() =>
                        requestSwitchProbe(selectedAtm, {
                          host: (settingsForm.switch_probe_host || "").trim(),
                          port: Number(settingsForm.switch_probe_port),
                        })
                      }
                      disabled={switchProbeBusyId === selectedAtm.atm_id}
                      className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                      title="فحص الوصول إلى السويتش من داخل الصراف"
                    >
                      <Network size={15} />
                      <span>{switchProbeBusyId === selectedAtm.atm_id ? "جار الطلب" : "فحص الآن"}</span>
                    </button>
                  </div>
                  <div className="grid gap-3 p-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-sm font-medium text-slate-700">Switch IP / Host</span>
                      <input
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.switch_probe_host ? "border-rose-400 bg-rose-50" : "border-slate-300 bg-white"
                        }`}
                        dir="ltr"
                        value={settingsForm.switch_probe_host || ""}
                        onChange={(event) =>
                          setSettingsForm((current) => ({ ...current, switch_probe_host: event.target.value }))
                        }
                        placeholder="172.16.25.75"
                      />
                      {fieldErrors.switch_probe_host && (
                        <span className="mt-1 block text-xs text-rose-700">{fieldErrors.switch_probe_host}</span>
                      )}
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-sm font-medium text-slate-700">Switch Port</span>
                      <input
                        type="number"
                        min="1"
                        max="65535"
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors.switch_probe_port ? "border-rose-400 bg-rose-50" : "border-slate-300 bg-white"
                        }`}
                        dir="ltr"
                        value={settingsForm.switch_probe_port || ""}
                        onChange={(event) =>
                          setSettingsForm((current) => ({ ...current, switch_probe_port: event.target.value }))
                        }
                        placeholder="10200"
                      />
                      {fieldErrors.switch_probe_port && (
                        <span className="mt-1 block text-xs text-rose-700">{fieldErrors.switch_probe_port}</span>
                      )}
                    </label>
                    <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm sm:col-span-2">
                      <div className="font-semibold text-slate-950" dir="ltr">
                        {(settingsForm.switch_probe_host || selectedAtm.switch_probe_host || "-").trim()}:
                        {settingsForm.switch_probe_port || selectedAtm.switch_probe_port || "-"}
                      </div>
                      {isSwitchTargetDirty(selectedAtm, settingsForm) ? (
                        <div className="mt-1 text-xs font-medium text-amber-700">
                          يوجد تغيير غير محفوظ في هدف فحص السويتش.
                        </div>
                      ) : null}
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2 py-1 text-xs ${getSwitchProbeTone(selectedAtm.last_switch_probe_status)}`}>
                          {formatSwitchProbe(selectedAtm)}
                        </span>
                        {selectedAtm.last_switch_probe_at && (
                          <span className="text-xs text-slate-500">{formatApiDate(selectedAtm.last_switch_probe_at)}</span>
                        )}
                      </div>
                      {selectedAtm.last_switch_probe_error && (
                        <div className="mt-1 truncate text-xs text-rose-700" title={selectedAtm.last_switch_probe_error}>
                          {selectedAtm.last_switch_probe_error}
                        </div>
                      )}
                    </div>
                  </div>
                </section>
              </div>

              <div className="mt-4">
                <SettingsGroup title="المسارات والفترات" icon={Clock3} meta="إعدادات متقدمة">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {settingsFields.map(([key, label, placeholder]) => (
                    <label key={key} className={key.endsWith("_path") ? "block md:col-span-2" : "block"}>
                      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
                      <input
                        className={`focus-ring w-full rounded-lg border px-3 py-2 ${
                          fieldErrors[key] ? "border-rose-400 bg-rose-50" : "border-slate-300"
                        }`}
                        dir={key.endsWith("_path") ? "ltr" : "rtl"}
                        value={settingsForm[key] || ""}
                        onChange={(event) => setSettingsForm((current) => ({ ...current, [key]: event.target.value }))}
                        placeholder={placeholder}
                      />
                      {fieldErrors[key] && <span className="mt-1 block text-xs text-rose-700">{fieldErrors[key]}</span>}
                    </label>
                  ))}
                </div>
                </SettingsGroup>
              </div>

              <div className="mt-4">
                <CassetteLayoutEditor
                  layout={settingsForm.cash_layout}
                  onChange={(nextLayout) => setSettingsForm((current) => ({ ...current, cash_layout: nextLayout }))}
                  title="عملة الكاسيتات"
                  fieldError={fieldErrors.cash_layout}
                />
              </div>

              <div className="mt-4">
                <SettingsGroup title="سجل الأحداث" icon={ScrollText} meta={`${atmEvents.length} حدث`}>
                  <AtmEventTimeline
                    events={atmEvents}
                    loading={loadingEvents}
                    onRefresh={() => loadEvents(selectedAtm.atm_id)}
                  />
                </SettingsGroup>
              </div>

              <div className="mt-4">
                <SettingsGroup title="تشخيص Agent" icon={Activity} meta="فحص عند الحاجة">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-slate-500">يعرض آخر حالة خدمة الـ Agent والأخطاء عند الحاجة.</div>
                  <button
                    type="button"
                    onClick={() => loadDiagnostics(selectedAtm.atm_id)}
                    disabled={loadingDiagnostics}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                    title="تحديث تشخيص الـ Agent"
                  >
                    <RefreshCw size={15} />
                    <span>{loadingDiagnostics ? "جار التحديث" : "تحديث"}</span>
                  </button>
                </div>
                <div>
                  {loadingDiagnostics && (
                    <div className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">
                      جار تحميل التشخيص...
                    </div>
                  )}
                  {!loadingDiagnostics && diagnostics && diagnostics.atm_id === selectedAtm.atm_id && (
                    <div className="space-y-3">
                      <div className={`rounded-lg border px-3 py-2 text-sm ${getDiagnosticsTone(diagnostics)}`}>
                        <div className="font-semibold">{diagnostics.summary}</div>
                        <div className="mt-1">{diagnostics.recommended_action}</div>
                      </div>
                      <div className="grid gap-3 text-sm md:grid-cols-3">
                        <div className="rounded-lg bg-slate-50 px-3 py-2">
                          <div className="text-slate-500">Reporting</div>
                          <div className="font-semibold text-slate-950">
                            {diagnostics.reporting_status === "reporting"
                              ? "Reporting"
                              : diagnostics.reporting_status === "never_reported"
                                ? "Never Reported"
                                : "Service Not Reporting"}
                          </div>
                        </div>
                        <div className="rounded-lg bg-slate-50 px-3 py-2">
                          <div className="text-slate-500">Service Status</div>
                          <div className="font-semibold text-slate-950">{diagnostics.service_status || "-"}</div>
                        </div>
                        <div className="rounded-lg bg-slate-50 px-3 py-2">
                          <div className="text-slate-500">Last Heartbeat</div>
                          <div className="font-semibold text-slate-950">{formatApiDate(diagnostics.last_heartbeat_at)}</div>
                          <div className="mt-1 text-xs text-slate-500">
                            {formatSeconds(diagnostics.seconds_since_last_seen)}
                          </div>
                        </div>
                      </div>
                      <div className="grid gap-3 text-sm md:grid-cols-2">
                        <div className="rounded-lg bg-slate-50 px-3 py-2">
                          <div className="text-slate-500">Last Server Error</div>
                          <div className="font-semibold text-slate-950">
                            {diagnostics.last_server_error ||
                              (diagnostics.reporting_status === "not_reporting"
                                ? "No server-side error reported. Check local agent.log on the ATM."
                                : "-")}
                          </div>
                          {diagnostics.last_server_error_at && (
                            <div className="mt-1 text-xs text-slate-500">{formatApiDate(diagnostics.last_server_error_at)}</div>
                          )}
                        </div>
                        <div className="rounded-lg bg-slate-50 px-3 py-2">
                          <div className="text-slate-500">Module Statuses</div>
                          <div className="font-semibold text-slate-950">
                            {Object.entries(selectedAtm.module_status_json || {}).length > 0
                              ? Object.entries(selectedAtm.module_status_json || {})
                                  .map(([name, status]) => `${name}: ${status}`)
                                  .join(" · ")
                              : "-"}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  {!loadingDiagnostics && (!diagnostics || diagnostics.atm_id !== selectedAtm.atm_id) && (
                    <div className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">
                      اضغط تحديث لعرض تشخيص الـ Agent.
                    </div>
                  )}
                </div>
                </SettingsGroup>
              </div>

              <div className="mt-4">
                <SettingsGroup
                  title="API Key"
                  icon={KeyRound}
                  meta="إجراء نادر"
                  defaultOpen={Boolean(generatedKey && generatedKeyAtmId === selectedAtm.atm_id)}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm text-slate-500">استخدمه فقط عند إعادة تثبيت Agent أو تغيير بيانات الاعتماد.</div>
                    <button
                      type="button"
                      onClick={regenerateApiKey}
                      disabled={regeneratingKey}
                      className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-amber-300 px-4 py-2 text-sm text-amber-800 hover:bg-amber-50 disabled:opacity-60"
                      title="توليد API Key جديد"
                    >
                      <KeyRound size={16} />
                      <span>{regeneratingKey ? "جاري التوليد..." : "Regenerate API Key"}</span>
                    </button>
                  </div>
                  {generatedKey && generatedKeyAtmId === selectedAtm.atm_id && (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
                      <div className="font-medium">API Key جديد للصراف {generatedKeyAtmId}</div>
                      <div className="mt-2 overflow-x-auto rounded border border-amber-200 bg-white px-2 py-1 font-mono text-xs" dir="ltr">
                        {buildInstallCommand(generatedKeyAtmId, generatedKey)}
                      </div>
                      <AgentInstallHint atm={generatedKeyAtm || selectedAtm} />
                      <button
                        type="button"
                        onClick={copyInstallCommand}
                        className="focus-ring mt-3 inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs text-amber-900 hover:bg-amber-100"
                        title="نسخ أمر التثبيت"
                      >
                        <Clipboard size={14} />
                        <span>Copy Install Command</span>
                      </button>
                      {copyMessage && <div className="mt-2 text-xs">{copyMessage}</div>}
                    </div>
                  )}
                </SettingsGroup>
              </div>

              {selectedAtm.last_config_error && (
                <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {selectedAtm.last_config_error}
                </div>
              )}
              {settingsMessage && (
                <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                  {settingsMessage}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-5 py-4">
              <div className="flex flex-wrap gap-2">
                <button
                  disabled={savingSettings}
                  className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                  title="حفظ إعدادات الصراف"
                >
                  <Save size={17} />
                  <span>{savingSettings ? "جار الحفظ..." : "حفظ"}</span>
                </button>
                <button
                  type="button"
                  onClick={regenerateApiKey}
                  disabled={regeneratingKey}
                  className="hidden"
                  title="توليد API Key جديد"
                >
                  <KeyRound size={17} />
                  <span>{regeneratingKey ? "جار التوليد..." : "Regenerate API Key"}</span>
                </button>
                {generatedKey && generatedKeyAtmId === selectedAtm.atm_id && (
                  <button
                    type="button"
                    onClick={copyInstallCommand}
                    className="hidden"
                    title="نسخ أمر التثبيت"
                  >
                    <Clipboard size={17} />
                    <span>Copy Install Command</span>
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={closeSettings}
                className="focus-ring min-h-11 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                إغلاق
              </button>
            </div>
          </form>
        </div>
      )}

      {switchProbeDialog?.open && (() => {
        const probe = switchProbeDialog.probe || {};
        const pending = !isFinalSwitchProbe(probe.status);
        return (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-6"
            role="dialog"
            aria-modal="true"
            onClick={() => setSwitchProbeDialog(null)}
          >
            <div
              className="w-full max-w-lg rounded-lg border border-slate-200 bg-white shadow-xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-950">
                    <Network size={18} />
                    <span>نتيجة فحص السويتش</span>
                  </div>
                  <div className="mt-1 text-sm text-slate-500">
                    {switchProbeDialog.atm?.name || switchProbeDialog.atm?.atm_id} · {switchProbeDialog.atm?.atm_id}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSwitchProbeDialog(null)}
                  className="focus-ring rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  title="إغلاق"
                >
                  <XCircle size={18} />
                </button>
              </div>

              <div className="space-y-4 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm ${getSwitchProbeTone(probe.status)}`}>
                    {formatSwitchProbeStatus(probe.status)}
                  </span>
                  <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-sm text-slate-700" dir="ltr">
                    {probe.host || "-"}:{probe.port || "-"}
                  </span>
                </div>

                {pending && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    تم إرسال طلب الفحص. بانتظار أن يسحبه الـ Agent وينفذه عبر TCP.
                  </div>
                )}

                {probe.status === "success" && (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                    تم الوصول إلى السويتش بنجاح.
                  </div>
                )}

                {probe.status === "failed" && (
                  <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                    فشل الوصول إلى السويتش.
                    {probe.error_message && <div className="mt-1 break-words">{probe.error_message}</div>}
                  </div>
                )}

                {switchProbeDialog.error && (
                  <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                    {switchProbeDialog.error}
                  </div>
                )}

                <div className="grid gap-3 text-sm sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="text-xs text-slate-500">Latency</div>
                    <div className="mt-1 font-semibold text-slate-950" dir="ltr">
                      {probe.latency_ms == null ? "-" : `${probe.latency_ms} ms`}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="text-xs text-slate-500">Status</div>
                    <div className="mt-1 font-semibold text-slate-950">{formatSwitchProbeStatus(probe.status)}</div>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="text-xs text-slate-500">وقت الطلب</div>
                    <div className="mt-1 text-slate-950">{formatApiDate(probe.requested_at)}</div>
                  </div>
                  <div className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="text-xs text-slate-500">وقت النتيجة</div>
                    <div className="mt-1 text-slate-950">{formatApiDate(probe.completed_at)}</div>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-4 py-3">
                <button
                  type="button"
                  onClick={refreshSwitchProbeDialog}
                  disabled={switchProbeDialog.refreshing}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
                  title="تحديث نتيجة الفحص"
                >
                  <RefreshCw size={16} className={switchProbeDialog.refreshing ? "animate-spin" : ""} />
                  <span>{switchProbeDialog.refreshing ? "جار التحديث..." : "تحديث"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setSwitchProbeDialog(null)}
                  className="focus-ring rounded-lg bg-teal-700 px-4 py-2 text-sm text-white hover:bg-teal-800"
                >
                  إغلاق
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </section>
  );
}
