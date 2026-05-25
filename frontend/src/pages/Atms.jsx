import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Clock3,
  KeyRound,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Trash2,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api, apiBaseUrl } from "../api/client";
import { formatApiDate, formatLastSeenAge, isRecentlyOnline } from "../api/time";

const emptyForm = { atm_id: "", name: "", vpn_ip: "", branch: "" };
const settingsFields = [
  ["media_path", "Media Path", "C:/ATM/Media"],
  ["backup_path", "Backup Path", "C:/ATM/Media_Backup"],
  ["temp_path", "Temp Path", "C:/ATM/Temp"],
  ["check_interval_seconds", "Media Check Interval", "300"],
  ["heartbeat_interval_seconds", "Heartbeat Interval Seconds", "60"],
  ["config_sync_interval_seconds", "Config Sync Interval", "120"],
  ["cash_read_interval_seconds", "Cash Read Interval", "120"],
  ["cash_stale_after_minutes", "Cash Stale After Minutes", "10"],
];
const cashLayoutProfiles = {
  yer_1000_4: [
    { cassette_no: 1, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
    { cassette_no: 2, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
    { cassette_no: 3, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
    { cassette_no: 4, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
  ],
  mixed_yer_usd_sar: [
    { cassette_no: 1, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
    { cassette_no: 2, currency: "YER", denomination: 1000, max_capacity: 2000, low_threshold: 300, critical_threshold: 100 },
    { cassette_no: 3, currency: "USD", denomination: 100, max_capacity: 2000, low_threshold: 100, critical_threshold: 30 },
    { cassette_no: 4, currency: "SAR", denomination: 100, max_capacity: 2000, low_threshold: 100, critical_threshold: 30 },
  ],
};
const fields = [
  ["atm_id", "ATM ID", "مثال: ATM-001", 2],
  ["name", "الاسم", "مثال: صراف الفرع الرئيسي", 2],
  ["vpn_ip", "IP عبر VPN", "مثال: 192.168.2.35", 3],
  ["branch", "الفرع", "مثال: lab1", 2],
];

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
  if (atm.last_config_error) return { label: "Failed", tone: "bg-rose-50 text-rose-700", icon: XCircle };
  if ((atm.applied_config_version || 0) < (atm.config_version || 0)) {
    return { label: "Pending Config Sync", tone: "bg-amber-50 text-amber-700", icon: Clock3 };
  }
  return { label: "Synced", tone: "bg-emerald-50 text-emerald-700", icon: CheckCircle2 };
}

function buildSettingsForm(atm) {
  const currentLayout = JSON.stringify(atm?.cash_layout_json || []);
  const mixedLayout = JSON.stringify(cashLayoutProfiles.mixed_yer_usd_sar);
  return {
    media_path: atm?.media_path || "",
    backup_path: atm?.backup_path || "",
    temp_path: atm?.temp_path || "",
    check_interval_seconds: String(atm?.check_interval_seconds || 300),
    heartbeat_interval_seconds: String(atm?.heartbeat_interval_seconds || 60),
    config_sync_interval_seconds: String(atm?.config_sync_interval_seconds || 120),
    media_update_enabled: atm?.media_update_enabled ?? true,
    cash_monitoring_enabled: atm?.cash_monitoring_enabled ?? false,
    atm_cash_mode: atm?.atm_cash_mode || "DISPENSE_ONLY",
    cash_provider: atm?.cash_provider || "mock",
    cash_layout_profile: currentLayout === mixedLayout ? "mixed_yer_usd_sar" : "yer_1000_4",
    cash_read_interval_seconds: String(atm?.cash_read_interval_seconds || 120),
    cash_stale_after_minutes: String(atm?.cash_stale_after_minutes || 10),
  };
}

function buildInstallCommand(atmId, apiKey) {
  return `atm-agent.exe install --server-url ${apiBaseUrl} --atm-id ${atmId} --api-key "${apiKey}"`;
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

function formatSeconds(seconds) {
  if (typeof seconds !== "number") return "لا يوجد اتصال";
  if (seconds < 60) return `قبل ${seconds} ثانية`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `قبل ${minutes} دقيقة`;
  const hours = Math.floor(minutes / 60);
  return `قبل ${hours} ساعة`;
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

export default function Atms({ atms, onChanged }) {
  const [form, setForm] = useState(emptyForm);
  const [selectedAtmId, setSelectedAtmId] = useState("");
  const [settingsForm, setSettingsForm] = useState({});
  const [settingsMessage, setSettingsMessage] = useState("");
  const [generatedKey, setGeneratedKey] = useState("");
  const [generatedKeyAtmId, setGeneratedKeyAtmId] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [regeneratingKey, setRegeneratingKey] = useState(false);
  const [deletingAtmId, setDeletingAtmId] = useState("");
  const [diagnostics, setDiagnostics] = useState(null);
  const [loadingDiagnostics, setLoadingDiagnostics] = useState(false);

  const selectedAtm = useMemo(
    () => atms.find((atm) => atm.atm_id === selectedAtmId) || null,
    [atms, selectedAtmId],
  );

  async function submit(event) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    setGeneratedKey("");
    setGeneratedKeyAtmId("");
    setCopyMessage("");

    const localErrors = validateForm(form);
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      setError("يرجى تصحيح الحقول المحددة.");
      return;
    }

    setLoading(true);
    try {
      const result = await api.createAtm({
        atm_id: form.atm_id.trim(),
        name: form.name.trim(),
        vpn_ip: form.vpn_ip.trim(),
        branch: form.branch.trim(),
      });
      setGeneratedKey(result.api_key);
      setGeneratedKeyAtmId(result.atm.atm_id);
      setForm(emptyForm);
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
    loadDiagnostics(atm.atm_id);
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

  async function saveSettings(event) {
    event.preventDefault();
    if (!selectedAtm) return;

    setSavingSettings(true);
    setSettingsMessage("");
    setError("");
    setFieldErrors({});

    try {
      const payload = {
        media_path: settingsForm.media_path.trim(),
        backup_path: settingsForm.backup_path.trim(),
        temp_path: settingsForm.temp_path.trim(),
        check_interval_seconds: Number(settingsForm.check_interval_seconds),
        heartbeat_interval_seconds: Number(settingsForm.heartbeat_interval_seconds),
        config_sync_interval_seconds: Number(settingsForm.config_sync_interval_seconds),
        media_update_enabled: Boolean(settingsForm.media_update_enabled),
        cash_monitoring_enabled: Boolean(settingsForm.cash_monitoring_enabled),
        atm_cash_mode: "DISPENSE_ONLY",
        cash_provider: settingsForm.cash_provider || "mock",
        cash_layout: cashLayoutProfiles[settingsForm.cash_layout_profile] || cashLayoutProfiles.yer_1000_4,
        cash_read_interval_seconds: Number(settingsForm.cash_read_interval_seconds),
        cash_stale_after_minutes: Number(settingsForm.cash_stale_after_minutes),
      };
      const updated = await api.updateAtm(selectedAtm.atm_id, payload);
      setSettingsForm(buildSettingsForm(updated));
      setSettingsMessage(`تم الحفظ. Config Version الآن ${updated.config_version}.`);
      onChanged();
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
      if (selectedAtmId === atm.atm_id) {
        setSelectedAtmId("");
        setSettingsForm({});
      }
      onChanged();
    } catch (err) {
      if (err.status === 409 && err.payload?.detail?.active_update_count) {
        const force = window.confirm(
          `يوجد ${err.payload.detail.active_update_count} تحديث نشط لهذا الصراف.\nهل تريد الحذف بالقوة؟`,
        );
        if (force) {
          try {
            await api.deleteAtm(atm.atm_id, true);
            if (selectedAtmId === atm.atm_id) {
              setSelectedAtmId("");
              setSettingsForm({});
            }
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
      setSettingsMessage("تم توليد API Key جديد. انسخ أمر التثبيت الآن؛ لن يظهر المفتاح مرة أخرى.");
      onChanged();
    } catch (err) {
      setError(err.message || "تعذر توليد API Key جديد");
    } finally {
      setRegeneratingKey(false);
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
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-slate-950">إدارة الصرافات</h1>
        <p className="text-sm text-slate-500">إضافة ومتابعة الصرافات المتصلة عبر VPN</p>
      </div>

      <form noValidate onSubmit={submit} className="mb-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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
        </div>
        {error && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
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
        {generatedKey && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            <div className="font-medium">API Key جديد للصراف {generatedKeyAtmId}</div>
            <div className="mt-2 overflow-x-auto rounded border border-amber-200 bg-white px-2 py-1 font-mono text-xs" dir="ltr">
              {generatedKey}
            </div>
            <div className="mt-2 overflow-x-auto rounded border border-amber-200 bg-white px-2 py-1 font-mono text-xs" dir="ltr">
              {installCommand}
            </div>
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
        <button
          disabled={loading}
          className="focus-ring mt-4 flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
          title="إضافة صراف"
        >
          <Plus size={17} />
          <span>{loading ? "جار الإضافة..." : "إضافة صراف"}</span>
        </button>
      </form>

      <div className="mb-6 rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold text-slate-950">
            <Settings2 size={18} />
            <span>ATM Settings</span>
          </div>
          <p className="mt-1 text-sm text-slate-500">تعديل مسارات الصور والنسخ الاحتياطي التي يسحبها الـ Agent تلقائياً</p>
        </div>
        {!selectedAtm && (
          <div className="px-4 py-8 text-center text-sm text-slate-500">اختر صرافاً من الجدول لتعديل الإعدادات</div>
        )}
        {selectedAtm && (
          <form noValidate onSubmit={saveSettings} className="p-4">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-medium text-slate-950">{selectedAtm.name}</div>
                <div className="text-sm text-slate-500">
                  {selectedAtm.atm_id} · Agent {selectedAtm.agent_version || "-"}
                </div>
              </div>
              {(() => {
                const status = getConfigStatus(selectedAtm);
                const Icon = status.icon;
                return (
                  <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${status.tone}`}>
                    <Icon size={15} />
                    {status.label}
                  </span>
                );
              })()}
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-2">
              <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium text-slate-700">Enable Media Update</span>
                <input
                  type="checkbox"
                  checked={Boolean(settingsForm.media_update_enabled)}
                  onChange={(event) =>
                    setSettingsForm((current) => ({ ...current, media_update_enabled: event.target.checked }))
                  }
                  className="h-4 w-4"
                />
              </label>
              <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium text-slate-700">Enable Cash Monitoring</span>
                <input
                  type="checkbox"
                  checked={Boolean(settingsForm.cash_monitoring_enabled)}
                  onChange={(event) =>
                    setSettingsForm((current) => ({ ...current, cash_monitoring_enabled: event.target.checked }))
                  }
                  className="h-4 w-4"
                />
              </label>
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <div className="text-slate-500">ATM Cash Mode</div>
                <div className="font-semibold text-slate-950">DISPENSE_ONLY</div>
              </div>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">CDM Provider</span>
                <select
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  value={settingsForm.cash_provider || "mock"}
                  onChange={(event) => setSettingsForm((current) => ({ ...current, cash_provider: event.target.value }))}
                >
                  <option value="mock">Mock Dispense Provider</option>
                  <option value="xfs_cdm">XFS CDM Provider</option>
                  <option value="vendor_cdm">Vendor CDM Provider</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">Cash Layout Profile</span>
                <select
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  value={settingsForm.cash_layout_profile || "yer_1000_4"}
                  onChange={(event) =>
                    setSettingsForm((current) => ({ ...current, cash_layout_profile: event.target.value }))
                  }
                >
                  <option value="yer_1000_4">YER 1000 Only - 4 Cassettes</option>
                  <option value="mixed_yer_usd_sar">YER 1000 / USD 100 / SAR 100 Mixed</option>
                </select>
              </label>
            </div>

            {settingsForm.cash_monitoring_enabled && (
              <div className="mb-4 overflow-hidden rounded-lg border border-slate-200">
                <div className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700">
                  Dispense cassette layout
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200 text-sm">
                    <thead className="bg-white text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-right font-medium">Cassette</th>
                        <th className="px-3 py-2 text-right font-medium">Currency</th>
                        <th className="px-3 py-2 text-right font-medium">Denomination</th>
                        <th className="px-3 py-2 text-right font-medium">Max</th>
                        <th className="px-3 py-2 text-right font-medium">Low</th>
                        <th className="px-3 py-2 text-right font-medium">Critical</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(cashLayoutProfiles[settingsForm.cash_layout_profile] || cashLayoutProfiles.yer_1000_4).map((item) => (
                        <tr key={item.cassette_no}>
                          <td className="px-3 py-2">{item.cassette_no}</td>
                          <td className="px-3 py-2">{item.currency}</td>
                          <td className="px-3 py-2">{item.denomination}</td>
                          <td className="px-3 py-2">{item.max_capacity}</td>
                          <td className="px-3 py-2">{item.low_threshold}</td>
                          <td className="px-3 py-2">{item.critical_threshold}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {settingsFields.map(([key, label, placeholder]) => (
                <label key={key} className="block">
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

            <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Config Version</div>
                <div className="font-semibold text-slate-950">{selectedAtm.config_version}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Applied Version</div>
                <div className="font-semibold text-slate-950">{selectedAtm.applied_config_version}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Last Config Sync</div>
                <div className="font-semibold text-slate-950">{formatApiDate(selectedAtm.last_config_sync_at)}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Last Heartbeat</div>
                <div className="font-semibold text-slate-950">{formatApiDate(selectedAtm.last_heartbeat_at)}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Latency</div>
                <div
                  className="font-semibold text-slate-950"
                  dir="ltr"
                  title={
                    isRecentlyOnline(selectedAtm)
                      ? "Latency from latest heartbeat"
                      : `Last stored latency: ${formatLatency(selectedAtm.latency_ms)}`
                  }
                >
                  {formatAtmLatency(selectedAtm)}
                </div>
              </div>
            </div>
            <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Active Updates</div>
                <div className="font-semibold text-slate-950">{selectedAtm.active_update_count || 0}</div>
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Last Agent Error</div>
                <div className="font-semibold text-slate-950">
                  {selectedAtm.last_agent_error || "-"}
                </div>
                {selectedAtm.last_agent_error_at && (
                  <div className="mt-1 text-xs text-slate-500">{formatApiDate(selectedAtm.last_agent_error_at)}</div>
                )}
              </div>
              <div className="rounded-lg bg-slate-50 px-3 py-2">
                <div className="text-slate-500">Reboot</div>
                <div className="font-semibold text-slate-950">
                  {selectedAtm.pending_reboot_count > 0 ? "Pending" : selectedAtm.last_reboot_status || "-"}
                </div>
                {selectedAtm.last_reboot_requested_at && (
                  <div className="mt-1 text-xs text-slate-500">{formatApiDate(selectedAtm.last_reboot_requested_at)}</div>
                )}
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-3 py-2">
                <div className="flex items-center gap-2 font-semibold text-slate-950">
                  <Activity size={17} />
                  <span>Agent Diagnostics</span>
                </div>
                <button
                  type="button"
                  onClick={() => loadDiagnostics(selectedAtm.atm_id)}
                  disabled={loadingDiagnostics}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                  title="تحديث تشخيص الـ Agent"
                >
                  <RefreshCw size={15} />
                  <span>{loadingDiagnostics ? "جار التحديث" : "تحديث"}</span>
                </button>
              </div>
              <div className="p-3">
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
                    <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                      <div className="mb-2 font-medium text-slate-950">Recent Agent Logs</div>
                      {diagnostics.recent_logs?.length > 0 ? (
                        <div className="space-y-2">
                          {diagnostics.recent_logs.slice(0, 3).map((log) => (
                            <div key={log.id} className="border-b border-slate-200 pb-2 last:border-b-0 last:pb-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className={`rounded-full px-2 py-0.5 text-xs ${
                                  log.level === "error"
                                    ? "bg-rose-50 text-rose-700"
                                    : log.level === "warning"
                                      ? "bg-amber-50 text-amber-700"
                                      : "bg-slate-100 text-slate-600"
                                }`}>
                                  {log.level}
                                </span>
                                <span className="text-xs text-slate-500">{formatApiDate(log.created_at)}</span>
                              </div>
                              <div className="mt-1 text-slate-700">{log.message}</div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-slate-500">لا توجد logs مرسلة من الـ Agent بعد.</div>
                      )}
                    </div>
                  </div>
                )}
                {!loadingDiagnostics && (!diagnostics || diagnostics.atm_id !== selectedAtm.atm_id) && (
                  <div className="rounded-lg bg-slate-50 px-3 py-4 text-center text-sm text-slate-500">
                    اضغط تحديث لعرض تشخيص الـ Agent.
                  </div>
                )}
              </div>
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

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                disabled={savingSettings}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
                title="حفظ إعدادات الصراف"
              >
                <Save size={17} />
                <span>{savingSettings ? "جار الحفظ..." : "Save"}</span>
              </button>
              <button
                type="button"
                onClick={regenerateApiKey}
                disabled={regeneratingKey}
                className="focus-ring inline-flex items-center gap-2 rounded-lg border border-amber-300 px-4 py-2 text-amber-800 hover:bg-amber-50 disabled:opacity-60"
                title="توليد API Key جديد"
              >
                <KeyRound size={17} />
                <span>{regeneratingKey ? "جار التوليد..." : "Regenerate API Key"}</span>
              </button>
              {generatedKey && generatedKeyAtmId === selectedAtm.atm_id && (
                <button
                  type="button"
                  onClick={copyInstallCommand}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-50"
                  title="نسخ أمر التثبيت"
                >
                  <Clipboard size={17} />
                  <span>Copy Install Command</span>
                </button>
              )}
            </div>
          </form>
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-right font-medium">ATM ID</th>
              <th className="px-4 py-3 text-right font-medium">الاسم</th>
              <th className="px-4 py-3 text-right font-medium">IP</th>
              <th className="px-4 py-3 text-right font-medium">الفرع</th>
              <th className="px-4 py-3 text-right font-medium">الحالة</th>
              <th className="px-4 py-3 text-right font-medium">Config Sync</th>
              <th className="px-4 py-3 text-right font-medium">Agent</th>
              <th className="px-4 py-3 text-right font-medium">Latency</th>
              <th className="px-4 py-3 text-right font-medium">آخر إصدار</th>
              <th className="px-4 py-3 text-right font-medium">آخر اتصال</th>
              <th className="px-4 py-3 text-right font-medium">آخر خطأ</th>
              <th className="px-4 py-3 text-right font-medium">إعدادات</th>
              <th className="px-4 py-3 text-right font-medium">حذف</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {atms.map((atm) => (
              <tr key={atm.atm_id}>
                <td className="px-4 py-3 font-mono text-slate-900">{atm.atm_id}</td>
                <td className="px-4 py-3">{atm.name}</td>
                <td className="px-4 py-3" dir="ltr">{atm.vpn_ip}</td>
                <td className="px-4 py-3">{atm.branch}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-1 text-xs ${isRecentlyOnline(atm) ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                    {isRecentlyOnline(atm) ? "online" : "offline"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {(() => {
                    const status = getConfigStatus(atm);
                    return <span className={`rounded-full px-2 py-1 text-xs ${status.tone}`}>{status.label}</span>;
                  })()}
                </td>
                <td className="px-4 py-3">{atm.agent_version || "-"}</td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-full px-2 py-1 text-xs ${getAtmLatencyTone(atm)}`}
                    dir="ltr"
                    title={
                      isRecentlyOnline(atm)
                        ? "Latency from latest heartbeat"
                        : `Last stored latency: ${formatLatency(atm.latency_ms)}`
                    }
                  >
                    {formatAtmLatency(atm)}
                  </span>
                </td>
                <td className="px-4 py-3">{atm.current_package_version || atm.last_image_version || "-"}</td>
                <td className="px-4 py-3">
                  <div>{formatApiDate(atm.last_heartbeat_at || atm.last_seen)}</div>
                  <div className="text-xs text-slate-500">{formatLastSeenAge(atm)}</div>
                </td>
                <td className="max-w-xs px-4 py-3">
                  <div className="truncate text-slate-700" title={atm.last_agent_error || ""}>
                    {atm.last_agent_error || "-"}
                  </div>
                  {atm.active_update_count > 0 && (
                    <div className="mt-1 text-xs text-amber-700">{atm.active_update_count} تحديث نشط</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => openSettings(atm)}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
                    title="إعدادات الصراف"
                  >
                    <Settings2 size={15} />
                    <span>فتح</span>
                  </button>
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => deleteAtm(atm)}
                    disabled={deletingAtmId === atm.atm_id}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                    title="حذف الصراف"
                  >
                    <Trash2 size={15} />
                    <span>{deletingAtmId === atm.atm_id ? "جار الحذف" : "حذف"}</span>
                  </button>
                </td>
              </tr>
            ))}
            {atms.length === 0 && (
              <tr>
                <td colSpan="13" className="px-4 py-8 text-center text-slate-500">لا توجد صرافات بعد</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
