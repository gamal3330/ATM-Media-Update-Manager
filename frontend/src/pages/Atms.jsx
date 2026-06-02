import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Clock3,
  KeyRound,
  Network,
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
  return { atm_id: "", name: "", vpn_ip: "", branch: "", cash_layout: buildCashLayout() };
}

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
    xfs_profile: atm?.xfs_profile || "ncr_aptra",
    xfs_logical_service: atm?.xfs_logical_service || xfsProfileDefaults[atm?.xfs_profile] || "MediaDispenser1",
    cash_layout: normalizeCashLayout(atm?.cash_layout_json),
    cash_read_interval_seconds: String(atm?.cash_read_interval_seconds || 120),
    cash_stale_after_minutes: String(atm?.cash_stale_after_minutes || 10),
    switch_probe_host: atm?.switch_probe_host || "172.16.25.75",
    switch_probe_port: String(atm?.switch_probe_port || 10200),
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

export default function Atms({ atms, onChanged }) {
  const [form, setForm] = useState(() => buildEmptyForm());
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
  const [switchProbeBusyId, setSwitchProbeBusyId] = useState("");
  const [switchProbeDialog, setSwitchProbeDialog] = useState(null);

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
        cash_layout: normalizeCashLayout(form.cash_layout),
      });
      setGeneratedKey(result.api_key);
      setGeneratedKeyAtmId(result.atm.atm_id);
      setForm(buildEmptyForm());
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
        switch_probe_host: settingsForm.switch_probe_host.trim(),
        switch_probe_port: Number(settingsForm.switch_probe_port),
        media_update_enabled: Boolean(settingsForm.media_update_enabled),
        cash_monitoring_enabled: Boolean(settingsForm.cash_monitoring_enabled),
        atm_cash_mode: "DISPENSE_ONLY",
        cash_provider: settingsForm.cash_provider || "mock",
        xfs_profile: settingsForm.xfs_profile || "ncr_aptra",
        xfs_logical_service: (settingsForm.xfs_logical_service || "").trim() || "MediaDispenser1",
        cash_layout: normalizeCashLayout(settingsForm.cash_layout),
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

  async function requestSwitchProbe(atm) {
    setSwitchProbeBusyId(atm.atm_id);
    setError("");
    setSettingsMessage("");
    try {
      const probe = await api.requestSwitchProbe(atm.atm_id);
      setSwitchProbeDialog({
        open: true,
        atm: { atm_id: atm.atm_id, name: atm.name },
        probe,
        error: "",
        refreshing: false,
      });
      setSettingsMessage(`تم إرسال طلب فحص السويتش للصراف ${atm.atm_id}: ${probe.host}:${probe.port}`);
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
        <div className="mt-4">
          <CassetteLayoutEditor
            layout={form.cash_layout}
            onChange={(nextLayout) => setForm((current) => ({ ...current, cash_layout: nextLayout }))}
            title="تحديد عملة كل Cassette"
            fieldError={fieldErrors.cash_layout}
          />
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

            <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-950">
                    <Network size={17} />
                    <span>إعدادات فحص السويتش</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    يتم الفحص من داخل الـAgent باستخدام TCP فقط، بدون Telnet أو CMD.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => requestSwitchProbe(selectedAtm)}
                  disabled={switchProbeBusyId === selectedAtm.atm_id}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                  title="فحص الوصول إلى السويتش من داخل الصراف"
                >
                  <Network size={15} />
                  <span>{switchProbeBusyId === selectedAtm.atm_id ? "جار الطلب" : "فحص الآن"}</span>
                </button>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
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
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                <span className={`rounded-full px-2 py-1 text-xs ${getSwitchProbeTone(selectedAtm.last_switch_probe_status)}`}>
                  {formatSwitchProbe(selectedAtm)}
                </span>
                {selectedAtm.last_switch_probe_at && (
                  <span className="text-xs text-slate-500">{formatApiDate(selectedAtm.last_switch_probe_at)}</span>
                )}
                {selectedAtm.last_switch_probe_error && (
                  <span className="max-w-full truncate text-xs text-rose-700" title={selectedAtm.last_switch_probe_error}>
                    {selectedAtm.last_switch_probe_error}
                  </span>
                )}
              </div>
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-2">
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
                <span className="mb-1 block text-sm font-medium text-slate-700">XFS Profile</span>
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
                    }));
                  }}
                >
                  <option value="ncr_aptra">NCR APTRA</option>
                  <option value="grg">GRG</option>
                  <option value="custom">Custom</option>
                </select>
                {fieldErrors.xfs_profile && (
                  <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_profile}</span>
                )}
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">XFS Logical Service</span>
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
                <span className="mt-1 block text-xs text-slate-500">
                  NCR غالبًا MediaDispenser1، وGRG من الفحص الحالي CDM.
                </span>
                {fieldErrors.xfs_logical_service && (
                  <span className="mt-1 block text-xs text-rose-700">{fieldErrors.xfs_logical_service}</span>
                )}
              </label>
            </div>

            <div className="mb-4">
              <CassetteLayoutEditor
                layout={settingsForm.cash_layout}
                onChange={(nextLayout) => setSettingsForm((current) => ({ ...current, cash_layout: nextLayout }))}
                title="تحديد عملة كل Cassette"
                fieldError={fieldErrors.cash_layout}
              />
            </div>

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
                <div className="flex items-center justify-between gap-2">
                  <div className="text-slate-500">Switch Probe</div>
                  <button
                    type="button"
                    onClick={() => requestSwitchProbe(selectedAtm)}
                    disabled={switchProbeBusyId === selectedAtm.atm_id}
                    className="focus-ring inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-60"
                    title="فحص الوصول إلى السويتش من داخل الصراف"
                  >
                    <Network size={13} />
                    <span>{switchProbeBusyId === selectedAtm.atm_id ? "جار الطلب" : "فحص"}</span>
                  </button>
                </div>
                <div className="mt-1 font-semibold text-slate-950" dir="ltr">
                  {selectedAtm.switch_probe_host}:{selectedAtm.switch_probe_port}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs ${getSwitchProbeTone(selectedAtm.last_switch_probe_status)}`}>
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

      <div className="space-y-3 lg:hidden">
        {atms.map((atm) => {
          const configStatus = getConfigStatus(atm);
          const online = isRecentlyOnline(atm);
          return (
            <article key={atm.atm_id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold text-slate-950">{atm.name}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{atm.atm_id}</div>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-1 text-xs ${online ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
                  {online ? "online" : "offline"}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">IP</div>
                  <div className="mt-1 truncate font-medium text-slate-900" dir="ltr">{atm.vpn_ip}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">الفرع</div>
                  <div className="mt-1 truncate font-medium text-slate-900">{atm.branch || "-"}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">Agent</div>
                  <div className="mt-1 truncate font-medium text-slate-900">{atm.agent_version || "-"}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">Latency</div>
                  <div className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${getAtmLatencyTone(atm)}`} dir="ltr">
                    {formatAtmLatency(atm)}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">Config Sync</div>
                  <div className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${configStatus.tone}`}>
                    {configStatus.label}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">Switch</div>
                  <div
                    className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs ${getSwitchProbeTone(atm.last_switch_probe_status)}`}
                    title={atm.last_switch_probe_error || ""}
                  >
                    {formatSwitchProbe(atm)}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-xs text-slate-500">آخر اتصال</div>
                  <div className="mt-1 font-medium text-slate-900">{formatLastSeenAge(atm)}</div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                <button
                  onClick={() => openSettings(atm)}
                  className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
                  title="إعدادات الصراف"
                >
                  <Settings2 size={16} />
                  <span>إعدادات</span>
                </button>
                <button
                  onClick={() => requestSwitchProbe(atm)}
                  disabled={switchProbeBusyId === atm.atm_id}
                  className="focus-ring inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
                  title={`فحص TCP من الصراف إلى ${atm.switch_probe_host}:${atm.switch_probe_port}`}
                >
                  <Network size={16} />
                  <span>{switchProbeBusyId === atm.atm_id ? "جار الطلب" : "فحص السويتش"}</span>
                </button>
                <button
                  onClick={() => deleteAtm(atm)}
                  disabled={deletingAtmId === atm.atm_id}
                  className="focus-ring col-span-2 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                  title="حذف الصراف"
                >
                  <Trash2 size={16} />
                  <span>{deletingAtmId === atm.atm_id ? "جار الحذف" : "حذف الصراف"}</span>
                </button>
              </div>
            </article>
          );
        })}
        {atms.length === 0 && (
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500 shadow-sm">
            لا توجد صرافات بعد
          </div>
        )}
      </div>

      <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm lg:block">
        <table className="min-w-[1120px] divide-y divide-slate-200 text-sm">
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
              <th className="px-4 py-3 text-right font-medium">Switch</th>
              <th className="px-4 py-3 text-right font-medium">آخر اتصال</th>
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
                  <span className={`rounded-full px-2 py-1 text-xs ${isRecentlyOnline(atm) ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
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
                <td className="px-4 py-3">
                  <div className="mb-1">
                    <span
                      className={`rounded-full px-2 py-1 text-xs ${getSwitchProbeTone(atm.last_switch_probe_status)}`}
                      title={atm.last_switch_probe_error || ""}
                    >
                      {formatSwitchProbe(atm)}
                    </span>
                  </div>
                  <button
                    onClick={() => requestSwitchProbe(atm)}
                    disabled={switchProbeBusyId === atm.atm_id}
                    className="focus-ring inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-60"
                    title={`فحص TCP من الصراف إلى ${atm.switch_probe_host}:${atm.switch_probe_port}`}
                  >
                    <Network size={13} />
                    <span>{switchProbeBusyId === atm.atm_id ? "جار الطلب" : "فحص"}</span>
                  </button>
                </td>
                <td className="px-4 py-3">
                  <div>{formatApiDate(atm.last_heartbeat_at || atm.last_seen)}</div>
                  <div className="text-xs text-slate-500">{formatLastSeenAge(atm)}</div>
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
                <td colSpan="12" className="px-4 py-8 text-center text-slate-500">لا توجد صرافات بعد</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

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
