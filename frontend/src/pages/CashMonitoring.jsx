import { AlertTriangle, Banknote, PackageCheck, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";

function statusTone(status) {
  const value = String(status || "").toUpperCase();
  if (value.includes("EMPTY") || value.includes("CRITICAL") || value.includes("MISSING") || value.includes("INOP")) {
    return "bg-rose-50 text-rose-700";
  }
  if (value.includes("LOW") || value.includes("HIGH") || value.includes("RETRACT")) return "bg-amber-50 text-amber-700";
  if (value.includes("MISMATCH")) return "bg-rose-50 text-rose-700";
  return "bg-emerald-50 text-emerald-700";
}

function formatCashValue(value) {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

function alertUnitLabel(alert) {
  if (alert.unit_no === 0) return "Reject/Retract";
  return `Cassette ${alert.unit_no}`;
}

function alertTypeLabel(type) {
  const known = {
    CASH_LOW: "نقد منخفض",
    CASH_CRITICAL: "نقد حرج",
    CASH_EMPTY: "نقد منتهي",
    CASSETTE_MISSING: "كاسيت غير موجود",
    CASSETTE_INOP: "كاسيت متوقف",
    CURRENCY_MISMATCH: "اختلاف العملة",
    DENOMINATION_MISMATCH: "اختلاف الفئة",
    REJECT_BIN_HIGH: "Reject مرتفع",
    REJECT_BIN_FULL: "Reject ممتلئ",
    RETRACT_OCCURRED: "Retract موجود",
  };
  return known[type] || type || "تنبيه";
}

const SUMMARY_DETAIL_META = {
  low: { title: "الصرافات منخفضة النقد", empty: "لا توجد صرافات منخفضة النقد حاليا." },
  critical: { title: "الصرافات الحرجة", empty: "لا توجد صرافات في حالة حرجة حاليا." },
  empty: { title: "الصرافات التي انتهى نقدها", empty: "لا توجد صرافات فارغة حاليا." },
};

const SUMMARY_ALERT_TYPES = {
  critical: new Set(["CASH_CRITICAL"]),
  empty: new Set(["CASH_EMPTY"]),
};

function getCashModuleStatus(atm) {
  return String(atm?.module_status_json?.cash_monitoring || (atm?.cash_monitoring_enabled ? "pending" : "disabled"));
}

function cashStatusTone(status) {
  const value = String(status || "").toLowerCase();
  if (value === "running") return "bg-emerald-50 text-emerald-700";
  if (value === "error") return "bg-rose-50 text-rose-700";
  if (value === "disabled") return "bg-slate-100 text-slate-600";
  return "bg-amber-50 text-amber-700";
}

const LAYOUT_REVIEW_CODES = new Set([
  "CURRENCY_MISMATCH",
  "DENOMINATION_MISMATCH",
  "MISSING_READING",
  "UNCONFIGURED_CASSETTE",
  "CONFIG_PENDING",
  "NO_READING",
  "CASH_MONITORING_DISABLED",
]);

function layoutVerificationStatus(verification) {
  if (!verification) return { label: "-", tone: "bg-slate-100 text-slate-600", matched: false };
  const issueCount = Number(verification.mismatch_count || 0);
  if (issueCount > 0) return { label: "غير مطابقة", tone: "bg-rose-50 text-rose-700", matched: false };
  if (String(verification.status || "").toLowerCase() === "no_reading") {
    return { label: "بانتظار قراءة", tone: "bg-amber-50 text-amber-700", matched: false };
  }
  return { label: "مطابقة", tone: "bg-emerald-50 text-emerald-700", matched: true };
}

function verificationIssueText(issue) {
  const cassette = issue.cassette_no ? `كاسيت ${issue.cassette_no}: ` : "";
  const values = issue.expected || issue.reported ? `المتوقع ${issue.expected || "-"}، المقروء ${issue.reported || "-"}` : "";
  const known = {
    CURRENCY_MISMATCH: "العملة لا تطابق إعدادات النظام",
    DENOMINATION_MISMATCH: "الفئة لا تطابق إعدادات النظام",
    MISSING_READING: "الكاسيت موجود في النظام ولم يظهر في قراءة الصراف",
    UNCONFIGURED_CASSETTE: "الصراف أرسل كاسيت غير معرّف في النظام",
    CONFIG_PENDING: "إعدادات الصراف لم تطبق على الـ Agent بعد",
    NO_READING: "لم تصل قراءة نقد من الصراف بعد",
    CASH_MONITORING_DISABLED: "مراقبة النقد غير مفعلة لهذا الصراف",
    CASH_LOW: "العدد أقل من حد التنبيه",
    CASH_CRITICAL: "العدد أقل من الحد الحرج",
    CASH_EMPTY: "الكاسيت فارغ",
    CASSETTE_MISSING: "الكاسيت غير موجود أو غير مقروء",
    CASSETTE_INOP: "الكاسيت في حالة عطل",
    REJECT_BIN_HIGH: "عدد reject مرتفع",
    REJECT_BIN_FULL: "صندوق reject ممتلئ",
    RETRACT_OCCURRED: "توجد أوراق مرتجعة في retract",
    REJECT_BIN_STATUS: "حالة reject تحتاج مراجعة",
    RETRACT_BIN_STATUS: "حالة retract تحتاج مراجعة",
  };
  return `${cassette}${known[issue.code] || issue.message}${values ? ` (${values})` : ""}`;
}

function configSyncLabel(atm) {
  if (!atm) return "-";
  return Number(atm.config_version) === Number(atm.applied_config_version) ? "Synced" : "Pending";
}

function getNoCashReason(details) {
  const atm = details?.atm;
  if (!atm) return "اختر صرافاً لعرض بيانات النقد.";
  if (!atm.cash_monitoring_enabled) return "مراقبة النقد غير مفعلة لهذا الصراف.";
  if (!atm.last_heartbeat_at) return "لم يصل Heartbeat من الـ Agent بعد. ثبّت الخدمة أو تأكد أنها تعمل.";
  if (Number(atm.config_version) !== Number(atm.applied_config_version)) return "إعدادات الصراف لم تطبق بعد. انتظر مزامنة الـ Agent أو أعد تشغيل الخدمة.";
  const status = getCashModuleStatus(atm).toLowerCase();
  if (status === "error") return atm.last_agent_error || "Cash Monitoring يعمل بخطأ. راجع Agent Logs أو جرّب xfs-cdm-read على الصراف.";
  if (status === "disabled") return "Cash Monitoring غير مفعل في إعدادات الصراف.";
  return `لا توجد snapshot نقد بعد. انتظر ${atm.cash_read_interval_seconds || 120} ثانية أو شغّل atm-agent.exe status على الصراف.`;
}

function readNowStatusMessage(command) {
  const status = String(command?.status || "pending").toLowerCase();
  const commandLabel = command?.id ? `#${command.id}` : "";
  if (status === "acknowledged") return `استلم الـ Agent طلب القراءة ${commandLabel} وهو قيد التنفيذ.`;
  if (status === "completed") return `اكتملت قراءة النقد ${commandLabel}. سيتم تحديث القيم الآن.`;
  if (status === "failed") return `فشلت قراءة النقد ${commandLabel}: ${command?.last_error || "راجع سجلات الـ Agent."}`;
  return `طلب قراءة النقد ${commandLabel} قيد الانتظار. إذا بقي معلقاً فحدّث نسخة الـ Agent وتأكد أن الخدمة تعمل.`;
}

function latestCashReadAt(details) {
  const timestamps = (details?.units || []).map((unit) => unit.read_at).filter(Boolean);
  if (details?.reject_retract?.read_at) timestamps.push(details.reject_retract.read_at);
  if (timestamps.length === 0) return null;
  return timestamps.sort((left, right) => Date.parse(right) - Date.parse(left))[0];
}

function parseTimestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? null : parsed;
}

function shouldShowFailedCashReadCommand(command, lastReadAt) {
  if (String(command?.status || "").toLowerCase() !== "failed") return false;
  const readTimestamp = parseTimestamp(lastReadAt);
  const commandTimestamp = parseTimestamp(command.completed_at || command.acknowledged_at || command.created_at);
  if (readTimestamp && commandTimestamp && readTimestamp > commandTimestamp) return false;
  return true;
}

function issueSummaryItems(summary) {
  return [
    { key: "low", label: "منخفض", value: summary?.cash_low_atms || 0, tone: "border-amber-200 bg-amber-50 text-amber-800" },
    { key: "critical", label: "حرج", value: summary?.cash_critical_atms || 0, tone: "border-rose-200 bg-rose-50 text-rose-700" },
    { key: "empty", label: "فارغ", value: summary?.cash_empty_atms || 0, tone: "border-rose-200 bg-rose-50 text-rose-700" },
  ].filter((item) => Number(item.value) > 0);
}

function QuietSummary({ summary, activeKey, onSelect }) {
  const items = issueSummaryItems(summary);
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 shadow-sm">
        الوضع النقدي مستقر
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => onSelect(item.key)}
          aria-pressed={activeKey === item.key}
          className={`focus-ring inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition ${
            activeKey === item.key ? "ring-2 ring-slate-300 ring-offset-1" : "hover:bg-white"
          } ${item.tone}`}
        >
          <span>{item.label}</span>
          <span className="font-semibold">{item.value}</span>
        </button>
      ))}
    </div>
  );
}

function SummaryDetailsPanel({ activeKey, items, onClose, onSelectAtm }) {
  if (!activeKey) return null;
  const meta = SUMMARY_DETAIL_META[activeKey];
  if (!meta) return null;

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-950">{meta.title}</div>
          <div className="mt-0.5 text-xs text-slate-500">{items.length} حالة معروضة</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="focus-ring rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          إغلاق
        </button>
      </div>
      {items.length === 0 ? (
        <div className="px-4 py-5 text-sm text-slate-500">{meta.empty}</div>
      ) : (
        <div className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => item.atmId && onSelectAtm(item.atmId)}
              className="block w-full px-4 py-3 text-right hover:bg-slate-50"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-950">{item.title}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.subtitle}</div>
                </div>
                {item.value && (
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.tone || "bg-slate-100 text-slate-700"}`}>
                    {item.value}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function BinSummary({ label, count, capacity, status }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-600">{label}</span>
        <span className={`rounded-full px-2 py-1 text-xs ${statusTone(status)}`}>{status || "-"}</span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <span className="text-2xl font-semibold text-slate-950">{count ?? "-"}</span>
        <span className="text-xs text-slate-500">/{capacity ?? "-"}</span>
      </div>
    </div>
  );
}

export default function CashMonitoring({ atms }) {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [activeSummaryKey, setActiveSummaryKey] = useState("");
  const [selectedAtmId, setSelectedAtmId] = useState("");
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [readNowLoading, setReadNowLoading] = useState(false);
  const [readNowMessage, setReadNowMessage] = useState("");
  const [error, setError] = useState("");

  const cashEnabledAtms = useMemo(() => atms.filter((atm) => atm.cash_monitoring_enabled), [atms]);
  const availableByCurrency = useMemo(() => {
    const totals = {};
    (details?.units || []).forEach((unit) => {
      const currency = unit.expected_currency || unit.reported_currency || "N/A";
      const denomination = Number(unit.expected_denomination || unit.reported_denomination || 0);
      totals[currency] = (totals[currency] || 0) + Number(unit.current_count || 0) * denomination;
    });
    return Object.entries(totals);
  }, [details]);
  const selectedAlerts = useMemo(() => {
    const selectedInternalId = details?.atm?.id;
    if (!selectedInternalId) return [];
    return alerts.filter((alert) => Number(alert.atm_id) === Number(selectedInternalId));
  }, [alerts, details]);
  const atmsByInternalId = useMemo(() => new Map(atms.map((atm) => [Number(atm.id), atm])), [atms]);
  const summaryDetailItems = useMemo(() => {
    if (!activeSummaryKey) return [];

    if (activeSummaryKey === "low") {
      return (summary?.low_cash_atms || []).map((item) => ({
        id: `low-${item.atm_id}-${item.cassette_no}`,
        atmId: item.atm_id,
        title: `${item.name} · Cassette ${item.cassette_no}`,
        subtitle: `${item.branch || "-"} · ${item.currency} ${item.denomination} · آخر قراءة ${formatApiDate(item.read_at)}`,
        value: `${item.current_count} / ${item.threshold_count}`,
        tone: "bg-amber-50 text-amber-800",
      }));
    }

    const types = SUMMARY_ALERT_TYPES[activeSummaryKey];
    return alerts
      .filter((alert) => !types || types.has(alert.alert_type))
      .map((alert) => {
        const atm = atmsByInternalId.get(Number(alert.atm_id));
        return {
          id: `alert-${alert.id}`,
          atmId: atm?.atm_id,
          title: `${atm?.name || `ATM ${alert.atm_id}`} · ${alertTypeLabel(alert.alert_type)}`,
          subtitle: `${alertUnitLabel(alert)} · الحالي ${alert.current_count} · الحد ${alert.threshold_count} · ${formatApiDate(alert.opened_at)}`,
          value: alert.alert_type,
          tone: statusTone(alert.alert_type),
        };
      });
  }, [activeSummaryKey, alerts, atmsByInternalId, summary]);
  const selectedAtmDiagnostics = details?.atm;
  const cashModuleStatus = getCashModuleStatus(selectedAtmDiagnostics);
  const selectedAtmForAction = selectedAtmDiagnostics || atms.find((atm) => atm.atm_id === selectedAtmId);
  const verification = details?.verification;
  const layoutStatus = layoutVerificationStatus(verification);
  const layoutReviewIssues = useMemo(
    () => (verification?.issues || []).filter((issue) => LAYOUT_REVIEW_CODES.has(issue.code)),
    [verification],
  );
  const lastReadAt = latestCashReadAt(details);
  const lastCashReadCommand = details?.last_cash_read_command;
  const showFailedCashReadCommand = shouldShowFailedCashReadCommand(lastCashReadCommand, lastReadAt);
  const canReadNow = Boolean(selectedAtmId && selectedAtmForAction?.cash_monitoring_enabled && !readNowLoading);

  async function load(preferredAtmId = selectedAtmId) {
    setLoading(true);
    setError("");
    try {
      const [summaryData, alertData] = await Promise.all([api.getCashSummary(), api.listCashAlerts()]);
      setSummary(summaryData);
      setAlerts(alertData);
      const nextAtmId = preferredAtmId || selectedAtmId || cashEnabledAtms[0]?.atm_id || atms[0]?.atm_id || "";
      if (nextAtmId) {
        setSelectedAtmId(nextAtmId);
        setDetails(await api.getCashAtm(nextAtmId));
      }
    } catch (err) {
      setError(err.message || "تعذر تحميل بيانات مراقبة النقد");
    } finally {
      setLoading(false);
    }
  }

  async function selectAtm(atmId) {
    setSelectedAtmId(atmId);
    setError("");
    setReadNowMessage("");
    try {
      setDetails(await api.getCashAtm(atmId));
    } catch (err) {
      setError(err.message || "تعذر تحميل بيانات الصراف");
    }
  }

  async function requestReadNow() {
    const atmId = selectedAtmId || details?.atm?.atm_id;
    if (!atmId || !selectedAtmForAction?.cash_monitoring_enabled) return;
    setReadNowLoading(true);
    setReadNowMessage("");
    setError("");
    try {
      const command = await api.requestCashReadNow(atmId);
      const message = readNowStatusMessage(command);
      if (String(command?.status || "").toLowerCase() === "failed") {
        setError(message);
      } else {
        setReadNowMessage(message);
      }
      window.setTimeout(() => {
        load(atmId);
      }, 5000);
    } catch (err) {
      setError(err.message || "تعذر إرسال طلب قراءة النقد");
    } finally {
      setReadNowLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [atms]);

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
            <Banknote size={25} />
            <span>مراقبة النقد</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={requestReadNow}
            disabled={!canReadNow}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
            title="طلب قراءة نقد فورية من الـ Agent"
          >
            <Banknote size={17} />
            <span>{readNowLoading ? "جار الطلب" : "قراءة نقد الآن"}</span>
          </button>
          <button
            onClick={() => load()}
            disabled={loading}
            className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            title="تحديث بيانات النقد"
          >
            <RefreshCw size={17} />
            <span>{loading ? "جار التحديث" : "تحديث"}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}
      {readNowMessage && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {readNowMessage}
        </div>
      )}

      <QuietSummary
        summary={summary}
        activeKey={activeSummaryKey}
        onSelect={(key) => setActiveSummaryKey((current) => (current === key ? "" : key))}
      />
      <SummaryDetailsPanel
        activeKey={activeSummaryKey}
        items={summaryDetailItems}
        onClose={() => setActiveSummaryKey("")}
        onSelectAtm={selectAtm}
      />

      <div className="mt-6 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">الصرافات</div>
          <div className="divide-y divide-slate-100">
            {atms.map((atm) => (
              <button
                key={atm.atm_id}
                onClick={() => selectAtm(atm.atm_id)}
                className={`block w-full px-4 py-3 text-right text-sm hover:bg-slate-50 ${
                  selectedAtmId === atm.atm_id ? "bg-teal-50" : ""
                }`}
              >
                <div className="font-medium text-slate-950">{atm.name}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {atm.atm_id} · {atm.cash_monitoring_enabled ? "CDM Enabled" : "CDM Disabled"}
                </div>
              </button>
            ))}
            {atms.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد صرافات</div>}
          </div>
        </div>

        <div className="min-w-0 space-y-4">
          {selectedAtmDiagnostics && (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-slate-950">{selectedAtmDiagnostics.name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {selectedAtmDiagnostics.atm_id} · آخر قراءة {formatApiDate(lastReadAt)}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${cashStatusTone(cashModuleStatus)}`}>
                    Cash: {cashModuleStatus}
                  </span>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${
                      Number(selectedAtmDiagnostics.config_version) === Number(selectedAtmDiagnostics.applied_config_version)
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    Config: {configSyncLabel(selectedAtmDiagnostics)}
                  </span>
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${layoutStatus.tone}`}>
                    {layoutStatus.label}
                  </span>
                </div>
              </div>
              {(!details?.units || details.units.length === 0) && (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
                  {getNoCashReason(details)}
                </div>
              )}
              {showFailedCashReadCommand && (
                <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700">
                  آخر طلب قراءة فشل: {lastCashReadCommand.last_error || "راجع سجلات الـ Agent."}
                </div>
              )}
            </div>
          )}

          {verification && layoutReviewIssues.length > 0 && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <AlertTriangle size={18} className="shrink-0" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">اختلاف في مطابقة الصناديق</span>
                      <span className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-rose-700 ring-1 ring-rose-200">
                        غير مطابقة
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-rose-700">
                      {verification.matched_units}/{verification.total_units} كاسيت مطابق · اختلافات {verification.mismatch_count || layoutReviewIssues.length}
                    </div>
                  </div>
                </div>
                <div className="text-xs text-rose-700">
                  {formatApiDate(verification.checked_at)}
                </div>
              </div>
              {layoutReviewIssues.length > 0 && (
                <details className="mt-2 border-t border-rose-200 pt-2 text-xs">
                  <summary className="cursor-pointer font-medium">عرض أسباب الاختلاف</summary>
                  <div className="mt-2 max-h-28 space-y-1 overflow-y-auto">
                    {layoutReviewIssues.slice(0, 6).map((issue, index) => (
                      <div key={`${issue.code}-${issue.cassette_no || "atm"}-${index}`} className="leading-5">
                        <span className="font-semibold">{issue.code}</span>
                        <span className="mx-2 text-rose-300">·</span>
                        <span>{verificationIssueText(issue)}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
              <PackageCheck size={17} />
              <span>الأرصدة الحالية</span>
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_150px_150px]">
              <div className="grid gap-2 sm:grid-cols-3">
                {availableByCurrency.map(([currency, value]) => (
                  <div key={currency} className="rounded-lg bg-slate-50 px-3 py-2">
                    <div className="text-xs font-medium text-slate-500">{currency}</div>
                    <div className="mt-1 font-semibold text-slate-950">{formatCashValue(value)}</div>
                  </div>
                ))}
                {availableByCurrency.length === 0 && <div className="text-sm text-slate-500">لا توجد قراءة نقد بعد</div>}
              </div>
              <BinSummary
                label="Reject Bin"
                count={details?.reject_retract?.reject_count}
                capacity={details?.reject_retract?.reject_max_capacity}
                status={details?.reject_retract?.reject_status}
              />
              <BinSummary
                label="Retract Bin"
                count={details?.reject_retract?.retract_count}
                capacity={details?.reject_retract?.retract_max_capacity}
                status={details?.reject_retract?.retract_status}
              />
            </div>
          </div>

          <div className="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-4 py-3">
              <div className="font-medium text-slate-950">صناديق السحب</div>
              <div className="mt-1 text-xs text-slate-500">
                {details?.atm ? `${details.atm.atm_id} · ${details.atm.atm_cash_mode || "DISPENSE_ONLY"}` : "اختر صرافاً"}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-[760px] divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-4 py-3 text-right font-medium">Cassette</th>
                    <th className="px-4 py-3 text-right font-medium">Cash</th>
                    <th className="px-4 py-3 text-right font-medium">Current</th>
                    <th className="px-4 py-3 text-right font-medium">Low / Critical</th>
                    <th className="px-4 py-3 text-right font-medium">Cassette Rejects</th>
                    <th className="px-4 py-3 text-right font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Last Read</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(details?.units || []).map((unit) => (
                    <tr key={unit.id}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-950">{unit.cassette_no}</div>
                        <div className="text-xs text-slate-500">{unit.cassette_name || unit.cassette_id || "-"}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div>
                          {unit.expected_currency} {unit.expected_denomination}
                        </div>
                        {unit.layout_match_status !== "MATCH" && (
                          <div className="mt-1 text-xs font-medium text-rose-700">
                            Reported: {unit.reported_currency} {unit.reported_denomination}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-950">{unit.current_count}</td>
                      <td className="px-4 py-3">{unit.low_threshold} / {unit.critical_threshold}</td>
                      <td className="px-4 py-3">{unit.reject_count}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full px-2 py-1 text-xs ${statusTone(unit.status)}`}>{unit.status}</span>
                        {unit.layout_match_status !== "MATCH" && (
                          <div className="mt-1 text-xs font-medium text-rose-700">{unit.layout_match_status}</div>
                        )}
                        {unit.physical_status && !["PRESENT", "OK"].includes(String(unit.physical_status).toUpperCase()) && (
                          <div className="mt-1 text-xs text-slate-500">{unit.physical_status}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">{formatApiDate(unit.read_at)}</td>
                    </tr>
                  ))}
                  {(!details || details.units.length === 0) && (
                    <tr>
                      <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                        {getNoCashReason(details)}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

      </div>
      </div>

      {selectedAlerts.length > 0 && (
        <div className="mt-6 rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-medium">
            <AlertTriangle size={18} />
            <span>التنبيهات المفتوحة</span>
          </div>
          <div className="divide-y divide-slate-100">
            {selectedAlerts.slice(0, 20).map((alert) => (
              <div key={alert.id} className="px-4 py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium text-slate-950">{alert.message}</div>
                  <span className={`rounded-full px-2 py-1 text-xs ${statusTone(alert.alert_type)}`}>{alert.alert_type}</span>
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {alertUnitLabel(alert)} · Current {alert.current_count} · Threshold {alert.threshold_count} · {formatApiDate(alert.opened_at)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
