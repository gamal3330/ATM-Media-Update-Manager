import { AlertTriangle, Bell, CheckCircle2, Mail, RefreshCw, Save, Send, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";

const defaultForm = {
  enabled: false,
  recipient_email: "",
  sender_email: "",
  smtp_host: "",
  smtp_port: 587,
  smtp_security: "starttls",
  smtp_username: "",
  smtp_password: "",
  notify_cash_low: true,
  notify_cash_empty: true,
};

const smtpSecurityOptions = [
  { value: "starttls", label: "STARTTLS" },
  { value: "ssl", label: "SSL" },
  { value: "none", label: "None" },
];

function buildForm(settings) {
  if (!settings) return defaultForm;
  return {
    enabled: Boolean(settings.enabled),
    recipient_email: settings.recipient_email || "",
    sender_email: settings.sender_email || "",
    smtp_host: settings.smtp_host || "",
    smtp_port: settings.smtp_port || 587,
    smtp_security: settings.smtp_security || "starttls",
    smtp_username: settings.smtp_username || "",
    smtp_password: "",
    notify_cash_low: Boolean(settings.notify_cash_low),
    notify_cash_empty: Boolean(settings.notify_cash_empty),
  };
}

function statusTone(status) {
  if (status === "sent") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-rose-50 text-rose-700";
  return "bg-amber-50 text-amber-700";
}

function deliveryErrorSummary(message) {
  const text = String(message || "");
  if (!text) return "";
  if (text.includes("Application-specific password required")) {
    return "Gmail يتطلب App Password بدل كلمة مرور الحساب.";
  }
  if (text.includes("Username and Password not accepted") || text.includes("Password not accepted")) {
    return "Gmail رفض اسم المستخدم أو كلمة المرور.";
  }
  if (text.includes("InvalidSecondFactor")) {
    return "الحساب يحتاج App Password لأن تسجيل الدخول الثنائي مفعل.";
  }
  return text.length > 110 ? `${text.slice(0, 110)}...` : text;
}

function SettingsBadge({ ok, label }) {
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium ${
        ok ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
      }`}
    >
      <Icon size={15} />
      {label}
    </span>
  );
}

function ToggleField({ checked, onChange, label }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`focus-ring inline-flex min-h-10 items-center gap-3 rounded-lg border px-3 py-2 text-sm font-semibold ${
        checked ? "border-teal-200 bg-teal-50 text-teal-800" : "border-slate-200 bg-white text-slate-600"
      }`}
      title={label}
    >
      <span className={`h-5 w-10 rounded-full p-0.5 transition ${checked ? "bg-teal-600" : "bg-slate-300"}`}>
        <span className={`block h-4 w-4 rounded-full bg-white transition ${checked ? "translate-x-0" : "-translate-x-5"}`} />
      </span>
      <span>{label}</span>
    </button>
  );
}

function normalizeRecipientRows(rows) {
  return (rows || []).map((row) => ({
    ...row,
    enabled: row.enabled !== false,
    recipient_email: row.recipient_email || "",
    effective_recipient_email: row.effective_recipient_email || "",
  }));
}

function RecipientRules({ rows, defaultEmail, saving, onChange, onSave }) {
  if (!rows.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
        لا توجد صرافات مضافة بعد.
      </div>
    );
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div className="font-semibold text-slate-950">مستلمو التنبيهات حسب الصراف</div>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="focus-ring inline-flex min-h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
          title="حفظ مستلمي الصرافات"
        >
          <Save size={15} />
          <span>{saving ? "جار الحفظ..." : "حفظ المستلمين"}</span>
        </button>
      </div>
      <div className="divide-y divide-slate-100">
        {rows.map((row) => {
          const effective = row.enabled
            ? row.recipient_email || defaultEmail || ""
            : "";
          return (
            <div key={row.atm_id} className="grid gap-3 px-4 py-3 lg:grid-cols-[minmax(180px,1fr)_minmax(240px,1.4fr)_130px]">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-950">{row.name}</div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span className="rounded-full bg-slate-100 px-2 py-1">{row.atm_id}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-1">{row.branch}</span>
                </div>
              </div>
              <label className="block">
                <span className="sr-only">بريد مستلم التنبيه</span>
                <input
                  type="email"
                  dir="ltr"
                  value={row.recipient_email}
                  onChange={(event) => onChange(row.atm_id, { recipient_email: event.target.value })}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder={defaultEmail ? "يستخدم البريد الافتراضي" : "recipient@example.com"}
                  disabled={!row.enabled}
                />
                <div className="mt-1 truncate text-xs text-slate-500" dir="ltr">
                  {row.enabled
                    ? effective || "لا يوجد بريد لهذا الصراف"
                    : "notifications disabled"}
                </div>
              </label>
              <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium text-slate-700">{row.enabled ? "مفعل" : "متوقف"}</span>
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(event) => onChange(row.atm_id, { enabled: event.target.checked })}
                  className="h-4 w-4"
                />
              </label>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DeliveryList({ deliveries }) {
  if (!deliveries.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
        لا توجد محاولات إرسال بعد.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="grid grid-cols-[140px_minmax(0,1fr)_140px] gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-600 max-md:hidden">
        <span>الحالة</span>
        <span>العنوان</span>
        <span>الوقت</span>
      </div>
      {deliveries.map((delivery) => (
        <div
          key={delivery.id}
          className="grid grid-cols-[140px_minmax(0,1fr)_140px] gap-3 border-b border-slate-100 px-3 py-3 last:border-b-0 max-md:block"
        >
          <div>
            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone(delivery.status)}`}>
              {delivery.status}
            </span>
          </div>
          <div className="min-w-0 max-md:mt-2">
            <div className="truncate font-semibold text-slate-950">{delivery.subject}</div>
            <div className="mt-1 truncate text-xs text-slate-500" dir="ltr">
              {delivery.recipient_email}
            </div>
            {delivery.error_message && (
              <details className="mt-1 text-xs text-rose-700">
                <summary className="cursor-pointer font-medium">{deliveryErrorSummary(delivery.error_message)}</summary>
                <div className="mt-1 max-h-28 overflow-y-auto rounded-md bg-rose-50 p-2 leading-5 text-rose-800" dir="ltr">
                  <span className="break-words">{delivery.error_message}</span>
                </div>
              </details>
            )}
          </div>
          <div className="text-sm text-slate-500 max-md:mt-2">{formatApiDate(delivery.sent_at || delivery.created_at)}</div>
        </div>
      ))}
    </div>
  );
}

export default function NotificationCenter() {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(defaultForm);
  const [recipientRows, setRecipientRows] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingRecipients, setSavingRecipients] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const hasStoredPassword = Boolean(settings?.has_smtp_password);
  const configured = Boolean(settings?.is_configured);
  const canSendTest = configured && Boolean(form.recipient_email.trim());
  const usesGmailSmtp = form.smtp_host.trim().toLowerCase() === "smtp.gmail.com";

  const enabledEvents = useMemo(
    () =>
      [
        form.notify_cash_low ? "انخفاض النقد" : null,
        form.notify_cash_empty ? "انتهاء النقد" : null,
      ].filter(Boolean),
    [form.notify_cash_empty, form.notify_cash_low],
  );

  function updateField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateRecipientRow(atmId, changes) {
    setRecipientRows((current) =>
      current.map((row) => (row.atm_id === atmId ? { ...row, ...changes } : row)),
    );
  }

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [settingsData, deliveryData, recipientData] = await Promise.all([
        api.getNotificationSettings(),
        api.listNotificationDeliveries(),
        api.listNotificationRecipients(),
      ]);
      setSettings(settingsData);
      setForm(buildForm(settingsData));
      setDeliveries(deliveryData);
      setRecipientRows(normalizeRecipientRows(recipientData));
    } catch (err) {
      setError(err.message || "تعذر تحميل مركز التنبيهات.");
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        enabled: form.enabled,
        recipient_email: form.recipient_email.trim() || null,
        sender_email: form.sender_email.trim() || null,
        smtp_host: form.smtp_host.trim() || null,
        smtp_port: Number(form.smtp_port),
        smtp_security: form.smtp_security,
        smtp_username: form.smtp_username.trim() || null,
        notify_cash_low: form.notify_cash_low,
        notify_cash_empty: form.notify_cash_empty,
      };
      if (form.smtp_password.trim()) {
        payload.smtp_password = form.smtp_password.trim();
      }
      const updated = await api.updateNotificationSettings(payload);
      setSettings(updated);
      setForm(buildForm(updated));
      setRecipientRows(normalizeRecipientRows(await api.listNotificationRecipients()));
      setMessage("تم حفظ مركز التنبيهات.");
    } catch (err) {
      setError(err.message || "تعذر حفظ مركز التنبيهات.");
    } finally {
      setSaving(false);
    }
  }

  async function saveRecipients() {
    setSavingRecipients(true);
    setMessage("");
    setError("");
    try {
      const updated = await api.updateNotificationRecipients(
        recipientRows.map((row) => ({
          atm_id: row.atm_id,
          enabled: row.enabled,
          recipient_email: row.recipient_email.trim() || null,
        })),
      );
      setRecipientRows(normalizeRecipientRows(updated));
      setMessage("تم حفظ مستلمي التنبيهات حسب الصراف.");
    } catch (err) {
      setError(err.message || "تعذر حفظ مستلمي التنبيهات.");
    } finally {
      setSavingRecipients(false);
    }
  }

  async function sendTestEmail() {
    setTesting(true);
    setMessage("");
    setError("");
    try {
      const delivery = await api.sendTestNotification();
      setDeliveries((current) => [delivery, ...current].slice(0, 50));
      setMessage(delivery.status === "sent" ? "تم إرسال رسالة الاختبار." : "فشل إرسال رسالة الاختبار.");
      if (delivery.status === "failed") setError(delivery.error_message || "فشل إرسال رسالة الاختبار.");
    } catch (err) {
      setError(err.message || "تعذر إرسال رسالة الاختبار.");
    } finally {
      setTesting(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
            <Bell size={26} />
            <span>مركز التنبيهات</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <SettingsBadge ok={Boolean(settings?.enabled)} label={settings?.enabled ? "مفعل" : "متوقف"} />
          <SettingsBadge ok={configured} label={configured ? "SMTP جاهز" : "SMTP غير مكتمل"} />
          <button
            type="button"
            onClick={loadData}
            disabled={loading}
            className="focus-ring inline-flex h-9 items-center gap-2 rounded-lg border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            title="تحديث"
          >
            <RefreshCw size={15} />
            <span>{loading ? "جار التحديث..." : "تحديث"}</span>
          </button>
        </div>
      </div>

      {message && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {message}
        </div>
      )}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,520px)]">
        <div className="space-y-4">
        <form noValidate onSubmit={saveSettings} className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div className="flex items-center gap-2 font-semibold text-slate-950">
              <Mail size={18} />
              <span>إعدادات البريد</span>
            </div>
            <div className="text-sm text-slate-500">
              {enabledEvents.length ? enabledEvents.join(" · ") : "لا توجد أحداث محددة"}
            </div>
          </div>

          <div className="space-y-4 p-4">
            <div className="flex flex-wrap gap-2">
              <ToggleField checked={form.enabled} onChange={(value) => updateField("enabled", value)} label="تفعيل الإرسال" />
              <ToggleField
                checked={form.notify_cash_low}
                onChange={(value) => updateField("notify_cash_low", value)}
                label="انخفاض النقد"
              />
              <ToggleField
                checked={form.notify_cash_empty}
                onChange={(value) => updateField("notify_cash_empty", value)}
                label="انتهاء النقد"
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">البريد الافتراضي</span>
                <input
                  type="email"
                  dir="ltr"
                  value={form.recipient_email}
                  onChange={(event) => updateField("recipient_email", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="cash.ops@example.com"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">البريد المرسل</span>
                <input
                  type="email"
                  dir="ltr"
                  value={form.sender_email}
                  onChange={(event) => updateField("sender_email", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="atm-manager@example.com"
                />
              </label>
            </div>

            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px_150px]">
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">SMTP Host</span>
                <input
                  dir="ltr"
                  value={form.smtp_host}
                  onChange={(event) => updateField("smtp_host", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="smtp.example.com"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">Port</span>
                <input
                  type="number"
                  min="1"
                  max="65535"
                  dir="ltr"
                  value={form.smtp_port}
                  onChange={(event) => updateField("smtp_port", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">Security</span>
                <select
                  value={form.smtp_security}
                  onChange={(event) => updateField("smtp_security", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                >
                  {smtpSecurityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">SMTP Username</span>
                <input
                  dir="ltr"
                  value={form.smtp_username}
                  onChange={(event) => updateField("smtp_username", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="optional"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-medium text-slate-700">
                  SMTP Password {hasStoredPassword ? "(محفوظ)" : ""}
                </span>
                <input
                  type="password"
                  dir="ltr"
                  value={form.smtp_password}
                  onChange={(event) => updateField("smtp_password", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder={hasStoredPassword ? "اتركه فارغا للإبقاء عليه" : ""}
                />
                {usesGmailSmtp && (
                  <div className="mt-1 text-xs leading-5 text-amber-700">
                    Gmail يحتاج App Password من إعدادات الحساب، وليس كلمة مرور Gmail العادية.
                  </div>
                )}
              </label>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
            <button
              type="button"
              onClick={sendTestEmail}
              disabled={testing || !canSendTest}
              className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-teal-300 px-4 py-2 text-sm font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-60"
              title="إرسال اختبار"
            >
              <Send size={16} />
              <span>{testing ? "جار الإرسال..." : "إرسال اختبار"}</span>
            </button>
            <button
              disabled={saving}
              className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              title="حفظ"
            >
              <Save size={16} />
              <span>{saving ? "جار الحفظ..." : "حفظ"}</span>
            </button>
          </div>
        </form>

        <RecipientRules
          rows={recipientRows}
          defaultEmail={form.recipient_email.trim()}
          saving={savingRecipients}
          onChange={updateRecipientRow}
          onSave={saveRecipients}
        />
        </div>

        <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
            <div className="font-semibold text-slate-950">آخر الإرسالات</div>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
              {deliveries.length}
            </span>
          </div>
          <div className="p-4">
            <DeliveryList deliveries={deliveries} />
          </div>
        </aside>
      </div>
    </section>
  );
}
