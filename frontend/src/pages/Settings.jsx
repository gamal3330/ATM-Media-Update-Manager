import {
  Activity,
  CheckCircle2,
  Clock3,
  Download,
  FileArchive,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, apiBaseUrl } from "../api/client";

const intervalFields = [
  {
    key: "check_interval_seconds",
    label: "Media Check Interval",
    unit: "ثانية",
    min: 30,
    max: 86400,
    defaultValue: 300,
  },
  {
    key: "config_sync_interval_seconds",
    label: "Config Sync Interval",
    unit: "ثانية",
    min: 30,
    max: 86400,
    defaultValue: 120,
  },
  {
    key: "cash_read_interval_seconds",
    label: "Cash Read Interval",
    unit: "ثانية",
    min: 30,
    max: 86400,
    defaultValue: 120,
  },
  {
    key: "cash_stale_after_minutes",
    label: "Cash Stale After",
    unit: "دقيقة",
    min: 1,
    max: 1440,
    defaultValue: 10,
  },
];

function commonAtmValue(atms, key, fallback) {
  if (!atms.length) return String(fallback);
  const values = [...new Set(atms.map((atm) => Number(atm[key])).filter((value) => Number.isFinite(value)))];
  return values.length === 1 ? String(values[0]) : "";
}

function buildIntervalForm(atms) {
  return Object.fromEntries(intervalFields.map((field) => [field.key, commonAtmValue(atms, field.key, field.defaultValue)]));
}

function StatusBadge({ ok, label }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${
        ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
      }`}
    >
      <Icon size={15} />
      {label}
    </span>
  );
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function Settings({ atms = [], onChanged, onOpenAgentDownloads }) {
  const [health, setHealth] = useState({ status: "unknown", message: "لم يتم الفحص بعد", checkedAt: "" });
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [downloadingSource, setDownloadingSource] = useState(false);
  const [downloadingExe, setDownloadingExe] = useState(false);
  const [savingIntervals, setSavingIntervals] = useState(false);
  const [intervalForm, setIntervalForm] = useState(() => buildIntervalForm(atms));
  const [intervalErrors, setIntervalErrors] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const healthUrl = `${apiBaseUrl}/api/health`;

  const healthOk = health.status === "ok";
  const hasMixedIntervals = useMemo(
    () => intervalFields.some((field) => commonAtmValue(atms, field.key, field.defaultValue) === ""),
    [atms],
  );

  function updateIntervalField(key, value) {
    setIntervalForm((current) => ({ ...current, [key]: value }));
    setIntervalErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  function validateIntervals() {
    const nextErrors = {};
    intervalFields.forEach((field) => {
      const value = Number(intervalForm[field.key]);
      if (!Number.isInteger(value)) {
        nextErrors[field.key] = "أدخل رقمًا صحيحًا.";
      } else if (value < field.min || value > field.max) {
        nextErrors[field.key] = `القيمة يجب أن تكون بين ${field.min} و ${field.max}.`;
      }
    });
    setIntervalErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }

  async function saveGlobalIntervals(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!validateIntervals()) {
      setError("يرجى تصحيح إعدادات الفترات الزمنية.");
      return;
    }

    const payload = Object.fromEntries(intervalFields.map((field) => [field.key, Number(intervalForm[field.key])]));
    const targets = atms.filter((atm) => intervalFields.some((field) => Number(atm[field.key]) !== payload[field.key]));
    if (targets.length === 0) {
      setMessage("إعدادات الفترات الزمنية مطابقة بالفعل على كل الصرافات.");
      return;
    }

    setSavingIntervals(true);
    try {
      for (const atm of targets) {
        await api.updateAtm(atm.atm_id, payload);
      }
      setMessage(`تم تطبيق إعدادات الفترات الزمنية على ${targets.length} صراف.`);
      await onChanged?.();
    } catch (err) {
      setError(err.message || "تعذر حفظ إعدادات الفترات الزمنية.");
    } finally {
      setSavingIntervals(false);
    }
  }

  async function checkHealth() {
    setCheckingHealth(true);
    setMessage("");
    setError("");
    try {
      const response = await fetch(healthUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      setHealth({
        status: payload.status === "ok" ? "ok" : "failed",
        message: payload.status === "ok" ? "Backend is reachable" : "Unexpected health response",
        checkedAt: new Date().toLocaleString(),
      });
    } catch (err) {
      setHealth({
        status: "failed",
        message: err.message || "Backend is not reachable",
        checkedAt: new Date().toLocaleString(),
      });
    } finally {
      setCheckingHealth(false);
    }
  }

  async function downloadSource() {
    setDownloadingSource(true);
    setMessage("");
    setError("");
    try {
      const blob = await api.downloadAgentSource();
      saveBlob(blob, "ATM-Agent-Build-Source.zip");
      setMessage("تم تنزيل حزمة بناء Agent.");
    } catch (err) {
      setError(err.message || "تعذر تنزيل حزمة Agent");
    } finally {
      setDownloadingSource(false);
    }
  }

  async function downloadExe() {
    setDownloadingExe(true);
    setMessage("");
    setError("");
    try {
      const blob = await api.downloadAgentExe();
      saveBlob(blob, "atm-agent.exe");
      setMessage("تم تنزيل atm-agent.exe.");
    } catch (err) {
      setError(err.message || "تعذر تنزيل atm-agent.exe");
    } finally {
      setDownloadingExe(false);
    }
  }

  useEffect(() => {
    checkHealth();
  }, []);

  useEffect(() => {
    if (!savingIntervals) setIntervalForm(buildIntervalForm(atms));
  }, [atms, savingIntervals]);

  return (
    <section>
      <div className="mb-5">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
          <SettingsIcon size={26} />
          <span>إعدادات النظام</span>
        </h1>
        <p className="text-sm text-slate-500">صحة النظام، ملخص الأمان، واختصارات الصيانة</p>
      </div>

      {message && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {message}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-4">
          <form noValidate onSubmit={saveGlobalIntervals} className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold text-slate-950">
                <Clock3 size={18} />
                <span>إعدادات الفترات المركزية</span>
              </div>
              {hasMixedIntervals && (
                <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                  توجد قيم مختلفة بين الصرافات
                </span>
              )}
            </div>
            <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4">
              {intervalFields.map((field) => (
                <label key={field.key} className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">{field.label}</span>
                  <div className="relative">
                    <input
                      type="number"
                      min={field.min}
                      max={field.max}
                      className={`focus-ring w-full rounded-lg border py-2 pl-3 pr-16 ${
                        intervalErrors[field.key] ? "border-rose-400 bg-rose-50" : "border-slate-300 bg-white"
                      }`}
                      dir="ltr"
                      value={intervalForm[field.key] || ""}
                      onChange={(event) => updateIntervalField(field.key, event.target.value)}
                      placeholder="قيم مختلفة"
                      required
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">
                      {field.unit}
                    </span>
                  </div>
                  {intervalErrors[field.key] && (
                    <span className="mt-1 block text-xs text-rose-700">{intervalErrors[field.key]}</span>
                  )}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
              <div className="text-sm text-slate-500">
                يتم تطبيق هذه القيم على كل الصرافات، ثم يستلمها الـ Agent في أول مزامنة إعدادات.
              </div>
              <button
                disabled={savingIntervals || atms.length === 0}
                className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                title="حفظ إعدادات الفترات المركزية"
              >
                <Save size={16} />
                <span>{savingIntervals ? "جار الحفظ..." : "حفظ وتطبيق"}</span>
              </button>
            </div>
          </form>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold text-slate-950">
                <Activity size={18} />
                <span>System Health</span>
              </div>
              <StatusBadge ok={healthOk} label={healthOk ? "Healthy" : "Needs Check"} />
            </div>
            <div className="grid gap-3 p-4 md:grid-cols-3">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-sm text-slate-500">Backend</div>
                <div className="mt-1 font-semibold text-slate-950">{healthOk ? "Reachable" : "Not reachable"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-sm text-slate-500">Last Check</div>
                <div className="mt-1 font-semibold text-slate-950">{health.checkedAt || "-"}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-sm text-slate-500">Response</div>
                <div className="mt-1 font-semibold text-slate-950">{health.message}</div>
              </div>
            </div>
            <div className="border-t border-slate-100 p-4">
              <button
                onClick={checkHealth}
                disabled={checkingHealth}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
                title="فحص صحة الخادم"
              >
                <RefreshCw size={17} />
                <span>{checkingHealth ? "جار الفحص..." : "Check Backend"}</span>
              </button>
            </div>
          </div>

        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">
              <Download size={18} />
              <span>Maintenance Shortcuts</span>
            </div>
            <div className="space-y-3 p-4">
              <button
                onClick={onOpenAgentDownloads}
                className="focus-ring flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-50"
                title="فتح صفحة تنزيل Agent"
              >
                <Download size={17} />
                <span>Open Agent Downloads</span>
              </button>
              <button
                onClick={downloadExe}
                disabled={downloadingExe}
                className="focus-ring flex w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
                title="تنزيل atm-agent.exe"
              >
                <Download size={17} />
                <span>{downloadingExe ? "جار التنزيل..." : "Download atm-agent.exe"}</span>
              </button>
              <button
                onClick={downloadSource}
                disabled={downloadingSource}
                className="focus-ring flex w-full items-center justify-center gap-2 rounded-lg border border-teal-300 px-4 py-2 text-teal-800 hover:bg-teal-50 disabled:opacity-60"
                title="تنزيل حزمة بناء Agent"
              >
                <FileArchive size={17} />
                <span>{downloadingSource ? "جار التنزيل..." : "Download Build Source"}</span>
              </button>
            </div>
          </div>

        </aside>
      </div>
    </section>
  );
}
