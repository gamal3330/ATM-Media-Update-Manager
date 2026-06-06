import {
  AlertTriangle,
  AtSign,
  Bell,
  CheckCircle2,
  Clock3,
  Mail,
  MessageCircle,
  QrCode,
  RefreshCw,
  Save,
  Search,
  Send,
  Server,
  Settings2,
  ShieldCheck,
  Users,
  XCircle,
} from "lucide-react";
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
  whatsapp_enabled: false,
  whatsapp_gateway_url: "http://127.0.0.1:3020",
  whatsapp_gateway_token: "",
  whatsapp_default_recipient: "",
  notify_cash_low: true,
  notify_cash_empty: true,
  notify_switch_disconnected: true,
  notify_whatsapp_disconnected: true,
};

const smtpSecurityOptions = [
  { value: "starttls", label: "STARTTLS" },
  { value: "ssl", label: "SSL" },
  { value: "none", label: "None" },
];

const deliveryFilters = [
  { id: "all", label: "الكل", type: "all" },
  { id: "whatsapp", label: "واتساب", type: "channel" },
  { id: "email", label: "البريد", type: "channel" },
  { id: "sent", label: "ناجحة", type: "status" },
  { id: "failed", label: "فاشلة", type: "status" },
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
    whatsapp_enabled: Boolean(settings.whatsapp_enabled),
    whatsapp_gateway_url: settings.whatsapp_gateway_url || "http://127.0.0.1:3020",
    whatsapp_gateway_token: "",
    whatsapp_default_recipient: settings.whatsapp_default_recipient || "",
    notify_cash_low: Boolean(settings.notify_cash_low),
    notify_cash_empty: Boolean(settings.notify_cash_empty),
    notify_switch_disconnected: settings.notify_switch_disconnected !== false,
    notify_whatsapp_disconnected: settings.notify_whatsapp_disconnected !== false,
  };
}

function statusTone(status) {
  if (status === "sent") return "bg-emerald-50 text-emerald-700 ring-emerald-100";
  if (status === "failed") return "bg-rose-50 text-rose-700 ring-rose-100";
  return "bg-amber-50 text-amber-700 ring-amber-100";
}

function statusIcon(status) {
  if (status === "sent") return CheckCircle2;
  if (status === "failed") return XCircle;
  return Clock3;
}

function deliveryStatusLabel(status) {
  if (status === "sent") return "مرسل";
  if (status === "failed") return "فشل";
  return status || "-";
}

function channelLabel(channel) {
  if (channel === "whatsapp") return "واتساب";
  if (channel === "email") return "البريد";
  return channel || "-";
}

function channelIcon(channel) {
  if (channel === "whatsapp") return MessageCircle;
  if (channel === "email") return Mail;
  return AtSign;
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

function normalizeRecipientRows(rows) {
  return (rows || []).map((row) => ({
    ...row,
    enabled: row.enabled !== false,
    recipient_email: row.recipient_email || "",
    effective_recipient_email: row.effective_recipient_email || "",
    whatsapp_number: row.whatsapp_number || "",
    whatsapp_numbers: row.whatsapp_numbers?.length ? row.whatsapp_numbers : row.whatsapp_number ? [row.whatsapp_number] : [],
    whatsapp_numbers_text: (row.whatsapp_numbers?.length ? row.whatsapp_numbers : row.whatsapp_number ? [row.whatsapp_number] : []).join(", "),
    effective_whatsapp_number: row.effective_whatsapp_number || "",
    effective_whatsapp_numbers: row.effective_whatsapp_numbers || [],
  }));
}

function parseWhatsAppNumbers(value) {
  return String(value || "")
    .split(/[,\n;]+/)
    .map((item) => item.trim().replace(/\s+/g, "").replace(/-/g, ""))
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index);
}

function whatsappStatusFromError(error) {
  if (error?.status === 404) {
    return {
      ok: false,
      ready: false,
      configured: false,
      status: "not_available",
      message: "مسار حالة واتساب غير متاح على السيرفر. حدّث السيرفر إلى آخر نسخة.",
    };
  }
  return {
    ok: false,
    ready: false,
    configured: false,
    status: "unreachable",
    message: error?.message || "تعذر قراءة حالة واتساب.",
  };
}

function buildSettingsPayload(form) {
  const payload = {
    enabled: form.enabled,
    recipient_email: form.recipient_email.trim() || null,
    sender_email: form.sender_email.trim() || null,
    smtp_host: form.smtp_host.trim() || null,
    smtp_port: Number(form.smtp_port),
    smtp_security: form.smtp_security,
    smtp_username: form.smtp_username.trim() || null,
    whatsapp_enabled: form.whatsapp_enabled,
    whatsapp_gateway_url: form.whatsapp_gateway_url.trim() || null,
    whatsapp_default_recipient: form.whatsapp_default_recipient.trim() || null,
    notify_cash_low: form.notify_cash_low,
    notify_cash_empty: form.notify_cash_empty,
    notify_switch_disconnected: form.notify_switch_disconnected,
    notify_whatsapp_disconnected: form.notify_whatsapp_disconnected,
  };
  if (form.smtp_password.trim()) {
    payload.smtp_password = form.smtp_password.trim();
  }
  if (form.whatsapp_gateway_token.trim()) {
    payload.whatsapp_gateway_token = form.whatsapp_gateway_token.trim();
  }
  return payload;
}

function StatCard({ icon: Icon, label, value, meta, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    teal: "border-teal-200 bg-teal-50 text-teal-900",
  };

  return (
    <article className={`min-h-[112px] rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-600">{label}</div>
        <Icon size={19} className="text-current opacity-75" />
      </div>
      <div className="mt-3 truncate text-2xl font-semibold leading-tight tracking-normal">{value}</div>
      {meta && <div className="mt-1 truncate text-xs text-slate-500">{meta}</div>}
    </article>
  );
}

function SectionCard({ title, icon: Icon, action, children, footer }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2 text-base font-semibold text-slate-950">
          {Icon && <Icon size={18} />}
          <span>{title}</span>
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
      {footer && <div className="border-t border-slate-100 px-4 py-3">{footer}</div>}
    </section>
  );
}

function FormField({ label, children, hint }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <div className="mt-1 text-xs leading-5 text-slate-500">{hint}</div>}
    </label>
  );
}

function ToggleField({ checked, onChange, label }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`focus-ring flex min-h-11 w-full items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm font-semibold ${
        checked ? "border-teal-200 bg-teal-50 text-teal-800" : "border-slate-200 bg-white text-slate-600"
      }`}
      title={label}
    >
      <span>{label}</span>
      <span className={`h-5 w-10 rounded-full p-0.5 transition ${checked ? "bg-teal-600" : "bg-slate-300"}`}>
        <span className={`block h-4 w-4 rounded-full bg-white transition ${checked ? "translate-x-0" : "-translate-x-5"}`} />
      </span>
    </button>
  );
}

function RecipientRules({ rows, defaultEmail, defaultWhatsapp, saving, search, onSearch, onChange, onSave }) {
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) =>
      [
        row.atm_id,
        row.name,
        row.branch,
        row.recipient_email,
        row.effective_recipient_email,
        row.whatsapp_number,
        row.whatsapp_numbers_text,
        row.effective_whatsapp_number,
        ...(row.effective_whatsapp_numbers || []),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [rows, search]);

  const enabledCount = rows.filter((row) => row.enabled).length;

  if (!rows.length) {
    return (
      <SectionCard title="مستلمو التنبيهات حسب الصراف" icon={Users}>
        <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
          لا توجد صرافات مضافة بعد.
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="مستلمو التنبيهات حسب الصراف"
      icon={Users}
      action={
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="focus-ring inline-flex min-h-9 items-center gap-2 rounded-lg bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
          title="حفظ مستلمي الصرافات"
        >
          <Save size={15} />
          <span>{saving ? "جاري الحفظ..." : "حفظ المستلمين"}</span>
        </button>
      }
    >
      <div className="mb-3 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
        <label className="relative block">
          <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <input
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            className="focus-ring w-full rounded-lg border border-slate-300 py-2 pl-3 pr-9 text-sm"
            placeholder="بحث باسم الصراف أو الفرع أو البريد"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600 xl:justify-end">
          <span className="rounded-full bg-teal-50 px-2.5 py-1 font-semibold text-teal-800">{enabledCount}/{rows.length} مفعلة</span>
          <span className="max-w-56 truncate rounded-full bg-slate-100 px-2.5 py-1" dir="ltr">
            {defaultEmail || "لا يوجد بريد افتراضي"}
          </span>
          <span className="max-w-56 truncate rounded-full bg-slate-100 px-2.5 py-1" dir="ltr">
            {defaultWhatsapp || "لا يوجد رقم واتساب افتراضي"}
          </span>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200">
        <div className="grid grid-cols-[minmax(170px,1fr)_minmax(230px,1.15fr)_minmax(230px,1.15fr)_112px] gap-3 border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-600 max-lg:hidden">
          <span>الصراف</span>
          <span>البريد</span>
          <span>أرقام WhatsApp</span>
          <span>الحالة</span>
        </div>
        <div className="divide-y divide-slate-100">
          {filteredRows.map((row) => {
            const effective = row.enabled ? row.recipient_email || defaultEmail || "" : "";
            const effectiveWhatsappNumbers = row.enabled
              ? row.whatsapp_numbers_text
                ? parseWhatsAppNumbers(row.whatsapp_numbers_text)
                : row.effective_whatsapp_numbers || []
              : [];
            return (
              <div
                key={row.atm_id}
                className="grid items-center gap-3 px-3 py-3 lg:grid-cols-[minmax(170px,1fr)_minmax(230px,1.15fr)_minmax(230px,1.15fr)_112px]"
              >
                <div className="min-w-0">
                  <div className="truncate font-semibold text-slate-950">{row.name}</div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                    <span className="rounded-full bg-slate-100 px-2 py-1">{row.atm_id}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-1">{row.branch}</span>
                  </div>
                </div>
                <div className="min-w-0">
                  <input
                    type="email"
                    dir="ltr"
                    value={row.recipient_email}
                    onChange={(event) => onChange(row.atm_id, { recipient_email: event.target.value })}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder={defaultEmail ? "البريد الافتراضي" : "recipient@example.com"}
                    disabled={!row.enabled}
                  />
                  <div className="mt-1 truncate px-1 text-xs text-slate-500" dir="ltr">
                    {row.enabled ? effective || "لا يوجد بريد" : "التنبيهات متوقفة"}
                  </div>
                </div>
                <div className="min-w-0">
                  <input
                    dir="ltr"
                    value={row.whatsapp_numbers_text}
                    onChange={(event) => onChange(row.atm_id, { whatsapp_numbers_text: event.target.value })}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="9677XXXXXXX, 9677YYYYYYY"
                    disabled={!row.enabled}
                    title={(row.effective_whatsapp_numbers || []).join(", ") || "أرقام واتساب"}
                  />
                  <div className="mt-1 truncate px-1 text-xs text-slate-500" dir="ltr">
                    {row.enabled ? effectiveWhatsappNumbers.join(", ") || defaultWhatsapp || "لا يوجد رقم" : "التنبيهات متوقفة"}
                  </div>
                </div>
                <label className="flex min-h-10 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
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
      </div>

      {!filteredRows.length && (
        <div className="mt-3 rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
          لا توجد نتائج مطابقة للبحث.
        </div>
      )}
    </SectionCard>
  );
}

function DeliveryList({ deliveries }) {
  if (!deliveries.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
        لا توجد محاولات إرسال مطابقة.
      </div>
    );
  }

  return (
    <div className="divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200 bg-white">
      {deliveries.map((delivery) => {
        const StatusIcon = statusIcon(delivery.status);
        const ChannelIcon = channelIcon(delivery.channel);
        return (
          <div key={delivery.id} className="grid gap-3 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_160px]">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${statusTone(delivery.status)}`}>
                  <StatusIcon size={13} />
                  <span>{deliveryStatusLabel(delivery.status)}</span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
                  <ChannelIcon size={13} />
                  <span>{channelLabel(delivery.channel)}</span>
                </span>
              </div>
              <div className="mt-2 truncate font-semibold text-slate-950">{delivery.subject}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span className="truncate" dir="ltr">
                  {delivery.recipient_email || "-"}
                </span>
                <span className="rounded-full bg-slate-50 px-2 py-0.5 text-slate-500">{delivery.event_type}</span>
              </div>
              {delivery.error_message && (
                <details className="mt-2 text-xs text-rose-700">
                  <summary className="cursor-pointer font-medium">{deliveryErrorSummary(delivery.error_message)}</summary>
                  <div className="mt-1 max-h-28 overflow-y-auto rounded-md bg-rose-50 p-2 leading-5 text-rose-800" dir="ltr">
                    <span className="break-words">{delivery.error_message}</span>
                  </div>
                </details>
              )}
            </div>
            <div className="text-sm font-medium text-slate-500 lg:text-left">{formatApiDate(delivery.sent_at || delivery.created_at)}</div>
          </div>
        );
      })}
    </div>
  );
}

function WhatsAppStatusPanel({ status, qr, ready }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-950">حالة WhatsApp</div>
          <div className="mt-1 text-xs text-slate-500">{status?.message || status?.status || "-"}</div>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            ready ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
          }`}
        >
          {ready ? "متصل" : status?.status || "غير متصل"}
        </span>
      </div>
      {qr?.qr_image && (
        <div className="mt-3 flex justify-center rounded-lg bg-white p-3">
          <img src={qr.qr_image} alt="WhatsApp QR" className="h-56 w-56" />
        </div>
      )}
    </div>
  );
}

function Notice({ tone, children }) {
  const isError = tone === "error";
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
        isError ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
      }`}
    >
      {isError && <AlertTriangle className="mt-0.5 shrink-0" size={16} />}
      <span>{children}</span>
    </div>
  );
}

export default function NotificationCenter() {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(defaultForm);
  const [recipientRows, setRecipientRows] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [whatsappStatus, setWhatsappStatus] = useState(null);
  const [whatsappQr, setWhatsappQr] = useState(null);
  const [recipientSearch, setRecipientSearch] = useState("");
  const [deliveryFilter, setDeliveryFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingRecipients, setSavingRecipients] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testingWhatsapp, setTestingWhatsapp] = useState(false);
  const [loadingQr, setLoadingQr] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const hasStoredPassword = Boolean(settings?.has_smtp_password);
  const configured = Boolean(settings?.is_configured);
  const whatsappConfigured = Boolean(settings?.is_whatsapp_configured);
  const canSendTest = configured && Boolean(form.recipient_email.trim());
  const canSendWhatsAppTest = whatsappConfigured && Boolean(form.whatsapp_default_recipient.trim());
  const usesGmailSmtp = form.smtp_host.trim().toLowerCase() === "smtp.gmail.com";
  const failedDeliveries = deliveries.filter((delivery) => delivery.status === "failed").length;
  const sentDeliveries = deliveries.filter((delivery) => delivery.status === "sent").length;
  const enabledRecipients = recipientRows.filter((row) => row.enabled).length;
  const whatsappReady = Boolean(whatsappStatus?.ready);

  const enabledEvents = useMemo(
    () =>
      [
        form.notify_cash_low ? "انخفاض النقد" : null,
        form.notify_cash_empty ? "انتهاء النقد" : null,
        form.notify_switch_disconnected ? "فصل الصراف عن السويتش" : null,
        form.notify_whatsapp_disconnected ? "فصل جلسة WhatsApp" : null,
      ].filter(Boolean),
    [form.notify_cash_empty, form.notify_cash_low, form.notify_switch_disconnected, form.notify_whatsapp_disconnected],
  );

  const visibleDeliveries = useMemo(() => {
    if (deliveryFilter === "all") return deliveries;
    const filter = deliveryFilters.find((item) => item.id === deliveryFilter);
    if (filter?.type === "channel") return deliveries.filter((delivery) => delivery.channel === deliveryFilter);
    return deliveries.filter((delivery) => delivery.status === deliveryFilter);
  }, [deliveries, deliveryFilter]);

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
      const [settingsData, deliveryData, recipientData, whatsappData] = await Promise.all([
        api.getNotificationSettings(),
        api.listNotificationDeliveries(),
        api.listNotificationRecipients(),
        api.getWhatsappStatus().catch(whatsappStatusFromError),
      ]);
      setSettings(settingsData);
      setForm(buildForm(settingsData));
      setDeliveries(deliveryData);
      setRecipientRows(normalizeRecipientRows(recipientData));
      setWhatsappStatus(whatsappData);
    } catch (err) {
      setError(err.message || "تعذر تحميل مركز التنبيهات.");
    } finally {
      setLoading(false);
    }
  }

  async function persistSettings(nextForm, successMessage) {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const updated = await api.updateNotificationSettings(buildSettingsPayload(nextForm));
      setSettings(updated);
      setForm(buildForm(updated));
      setRecipientRows(normalizeRecipientRows(await api.listNotificationRecipients()));
      setMessage(successMessage);
    } catch (err) {
      setError(err.message || "تعذر حفظ مركز التنبيهات.");
    } finally {
      setSaving(false);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    await persistSettings(form, "تم حفظ مركز التنبيهات.");
  }

  async function saveWhatsAppSettings() {
    const nextForm = { ...form, whatsapp_enabled: true };
    setForm(nextForm);
    await persistSettings(nextForm, "تم تفعيل وحفظ واتساب.");
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
          whatsapp_numbers: parseWhatsAppNumbers(row.whatsapp_numbers_text || row.whatsapp_number),
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

  async function refreshWhatsappQr() {
    setLoadingQr(true);
    setMessage("");
    setError("");
    try {
      const qr = await api.getWhatsappQr();
      setWhatsappQr(qr);
      setWhatsappStatus(qr);
      if (!qr.qr_image && qr.ready) {
        setMessage("WhatsApp متصل ولا يحتاج QR جديد.");
      } else if (!qr.qr_image) {
        setError(qr.message || "لم يصدر QR من خدمة WhatsApp بعد. تأكد أن الخدمة تعمل.");
      }
    } catch (err) {
      const status = whatsappStatusFromError(err);
      setWhatsappStatus(status);
      setError(status.message || "تعذر جلب QR الخاص بـ WhatsApp.");
    } finally {
      setLoadingQr(false);
    }
  }

  async function sendTestWhatsApp() {
    setTestingWhatsapp(true);
    setMessage("");
    setError("");
    try {
      const delivery = await api.sendWhatsAppTestNotification();
      setDeliveries((current) => [delivery, ...current].slice(0, 50));
      setMessage(delivery.status === "sent" ? "تم إرسال رسالة اختبار WhatsApp." : "فشل إرسال رسالة اختبار WhatsApp.");
      if (delivery.status === "failed") setError(delivery.error_message || "فشل إرسال رسالة اختبار WhatsApp.");
    } catch (err) {
      setError(err.message || "تعذر إرسال رسالة اختبار WhatsApp.");
    } finally {
      setTestingWhatsapp(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
          <Bell size={26} />
          <span>مركز التنبيهات</span>
        </h1>
        <button
          type="button"
          onClick={loadData}
          disabled={loading}
          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          title="تحديث"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          <span>{loading ? "جاري التحديث..." : "تحديث"}</span>
        </button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          icon={ShieldCheck}
          label="الإرسال"
          value={settings?.enabled ? "مفعل" : "متوقف"}
          meta={enabledEvents.length ? enabledEvents.join(" · ") : "لا توجد أحداث محددة"}
          tone={settings?.enabled ? "emerald" : "slate"}
        />
        <StatCard
          icon={Server}
          label="SMTP"
          value={configured ? "جاهز" : "غير مكتمل"}
          meta={form.smtp_host || "لم يتم تحديد السيرفر"}
          tone={configured ? "emerald" : "amber"}
        />
        <StatCard
          icon={MessageCircle}
          label="WhatsApp"
          value={whatsappReady ? "متصل" : form.whatsapp_enabled ? "يحتاج QR" : "متوقف"}
          meta={whatsappStatus?.status || form.whatsapp_gateway_url || "غير مهيأ"}
          tone={whatsappReady ? "emerald" : form.whatsapp_enabled ? "amber" : "slate"}
        />
        <StatCard
          icon={Users}
          label="المستلمون"
          value={`${enabledRecipients}/${recipientRows.length}`}
          meta={form.recipient_email || "لا يوجد بريد افتراضي"}
          tone={enabledRecipients ? "teal" : "slate"}
        />
        <StatCard
          icon={Clock3}
          label="آخر الإرسالات"
          value={`${sentDeliveries} / ${failedDeliveries}`}
          meta="ناجحة / فاشلة"
          tone={failedDeliveries ? "rose" : "emerald"}
        />
      </div>

      {message && (
        <Notice>{message}</Notice>
      )}
      {error && (
        <Notice tone="error">{error}</Notice>
      )}

      <div className="grid gap-4 2xl:grid-cols-[minmax(380px,500px)_minmax(0,1fr)]">
        <form noValidate onSubmit={saveSettings} className="space-y-4 2xl:sticky 2xl:top-4 2xl:self-start">
          <SectionCard
            title="التنبيهات"
            icon={Settings2}
            footer={
              <div className="flex flex-wrap items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={sendTestEmail}
                  disabled={testing || !canSendTest}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-teal-300 px-4 py-2 text-sm font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-60"
                  title="إرسال اختبار"
                >
                  <Send size={16} />
                  <span>{testing ? "جاري الإرسال..." : "إرسال اختبار"}</span>
                </button>
                <button
                  disabled={saving}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                  title="حفظ"
                >
                  <Save size={16} />
                  <span>{saving ? "جاري الحفظ..." : "حفظ الإعدادات"}</span>
                </button>
              </div>
            }
          >
            <div className="space-y-4">
              <div className="grid gap-2 sm:grid-cols-2">
                <ToggleField checked={form.enabled} onChange={(value) => updateField("enabled", value)} label="تفعيل الإرسال" />
                <ToggleField
                  checked={form.notify_cash_low}
                  onChange={(value) => updateField("notify_cash_low", value)}
                  label="تنبيه انخفاض النقد"
                />
                <ToggleField
                  checked={form.notify_cash_empty}
                  onChange={(value) => updateField("notify_cash_empty", value)}
                  label="تنبيه انتهاء النقد"
                />
                <ToggleField
                  checked={form.notify_switch_disconnected}
                  onChange={(value) => updateField("notify_switch_disconnected", value)}
                  label="تنبيه فصل الصراف عن السويتش"
                />
                <ToggleField
                  checked={form.notify_whatsapp_disconnected}
                  onChange={(value) => updateField("notify_whatsapp_disconnected", value)}
                  label="تنبيه فصل جلسة WhatsApp"
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <FormField label="البريد الافتراضي">
                  <input
                    type="email"
                    dir="ltr"
                    value={form.recipient_email}
                    onChange={(event) => updateField("recipient_email", event.target.value)}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                    placeholder="cash.ops@example.com"
                  />
                </FormField>
                <FormField label="البريد المرسل">
                  <input
                    type="email"
                    dir="ltr"
                    value={form.sender_email}
                    onChange={(event) => updateField("sender_email", event.target.value)}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                    placeholder="atm-manager@example.com"
                  />
                </FormField>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="البريد SMTP" icon={Server}>
            <div className="grid gap-3">
              <FormField label="SMTP Host">
                <input
                  dir="ltr"
                  value={form.smtp_host}
                  onChange={(event) => updateField("smtp_host", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="smtp.example.com"
                />
              </FormField>

              <div className="grid gap-3 sm:grid-cols-[1fr_1fr]">
                <FormField label="Port">
                  <input
                    type="number"
                    min="1"
                    max="65535"
                    dir="ltr"
                    value={form.smtp_port}
                    onChange={(event) => updateField("smtp_port", event.target.value)}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </FormField>
                <FormField label="Security">
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
                </FormField>
              </div>

              <FormField label="SMTP Username">
                <input
                  dir="ltr"
                  value={form.smtp_username}
                  onChange={(event) => updateField("smtp_username", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="optional"
                />
              </FormField>
              <FormField
                label={`SMTP Password ${hasStoredPassword ? "(محفوظ)" : ""}`}
                hint={usesGmailSmtp ? "Gmail يحتاج App Password." : null}
              >
                <input
                  type="password"
                  dir="ltr"
                  value={form.smtp_password}
                  onChange={(event) => updateField("smtp_password", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder={hasStoredPassword ? "اتركه فارغاً للإبقاء عليه" : ""}
                />
              </FormField>
            </div>
          </SectionCard>
          <SectionCard
            title="واتساب"
            icon={MessageCircle}
            footer={
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={refreshWhatsappQr}
                    disabled={loadingQr || !settings?.whatsapp_gateway_url}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                    title="عرض QR"
                  >
                    <QrCode size={16} />
                    <span>{loadingQr ? "جاري الجلب..." : "عرض QR"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={sendTestWhatsApp}
                    disabled={testingWhatsapp || !canSendWhatsAppTest}
                    className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-teal-300 px-4 py-2 text-sm font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-60"
                    title="إرسال اختبار WhatsApp"
                  >
                    <Send size={16} />
                    <span>{testingWhatsapp ? "جاري الإرسال..." : "إرسال اختبار"}</span>
                  </button>
                </div>
                <button
                  type="button"
                  onClick={saveWhatsAppSettings}
                  disabled={saving}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                  title="حفظ إعدادات واتساب"
                >
                  <Save size={16} />
                  <span>{saving ? "جاري الحفظ..." : "تفعيل وحفظ واتساب"}</span>
                </button>
              </div>
            }
          >
            <div className="space-y-4">
              <ToggleField
                checked={form.whatsapp_enabled}
                onChange={(value) => updateField("whatsapp_enabled", value)}
                label="تفعيل WhatsApp"
              />

              <FormField label="Gateway URL">
                <input
                  dir="ltr"
                  value={form.whatsapp_gateway_url}
                  onChange={(event) => updateField("whatsapp_gateway_url", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="http://127.0.0.1:3020"
                />
              </FormField>

              <FormField label="Gateway Token">
                <input
                  type="password"
                  dir="ltr"
                  value={form.whatsapp_gateway_token}
                  onChange={(event) => updateField("whatsapp_gateway_token", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder={settings?.has_whatsapp_gateway_token ? "اتركه فارغاً للإبقاء عليه" : "اختياري"}
                />
              </FormField>

              <FormField label="رقم واتساب الافتراضي">
                <input
                  dir="ltr"
                  value={form.whatsapp_default_recipient}
                  onChange={(event) => updateField("whatsapp_default_recipient", event.target.value)}
                  className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  placeholder="9677XXXXXXX"
                />
              </FormField>

              <WhatsAppStatusPanel status={whatsappStatus} qr={whatsappQr} ready={whatsappReady} />
            </div>
          </SectionCard>
        </form>

        <div className="space-y-4">
          <RecipientRules
            rows={recipientRows}
            defaultEmail={form.recipient_email.trim()}
            defaultWhatsapp={form.whatsapp_default_recipient.trim()}
            saving={savingRecipients}
            search={recipientSearch}
            onSearch={setRecipientSearch}
            onChange={updateRecipientRow}
            onSave={saveRecipients}
          />

          <SectionCard
            title="آخر الإرسالات"
            icon={AtSign}
            action={
              <div className="flex flex-wrap gap-1">
                {deliveryFilters.map((filter) => (
                  <button
                    key={filter.id}
                    type="button"
                    onClick={() => setDeliveryFilter(filter.id)}
                    className={`focus-ring rounded-lg px-3 py-1.5 text-xs font-semibold ${
                      deliveryFilter === filter.id
                        ? "bg-slate-900 text-white"
                        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>
            }
          >
            <DeliveryList deliveries={visibleDeliveries} />
          </SectionCard>
        </div>
      </div>
    </section>
  );
}
