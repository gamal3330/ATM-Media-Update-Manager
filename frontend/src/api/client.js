function resolveApiBase() {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL.replace(/\/$/, "");
  }

  if (typeof window === "undefined") return "http://localhost:8001";

  const { protocol, hostname, port, origin } = window.location;
  if (!port || port === "8001") return origin;
  if (port === "5175") return `${protocol}//${hostname}:8001`;
  return origin;
}

const API_BASE = resolveApiBase();
export const apiBaseUrl = API_BASE;
export const authTokenKey = "qib_atm_manager_token";
const legacyAuthTokenKey = "atm_media_token";

export function getAuthToken() {
  const token = localStorage.getItem(authTokenKey);
  if (token) return token;
  const legacyToken = localStorage.getItem(legacyAuthTokenKey);
  if (legacyToken) {
    localStorage.setItem(authTokenKey, legacyToken);
    localStorage.removeItem(legacyAuthTokenKey);
  }
  return legacyToken;
}

export function setAuthToken(token) {
  localStorage.setItem(authTokenKey, token);
  localStorage.removeItem(legacyAuthTokenKey);
}

export function clearAuthToken() {
  localStorage.removeItem(authTokenKey);
  localStorage.removeItem(legacyAuthTokenKey);
}

export class ApiError extends Error {
  constructor(message, status, payload, fieldErrors = {}, details = []) {
    super(message);
    this.status = status;
    this.payload = payload;
    this.fieldErrors = fieldErrors;
    this.details = details;
  }
}

const fieldLabels = {
  atm_id: "ATM ID",
  name: "الاسم",
  vpn_ip: "IP عبر VPN",
  branch: "الفرع",
  media_path: "Media Path",
  backup_path: "Backup Path",
  temp_path: "Temp Path",
  check_interval_seconds: "Check Interval Seconds",
  heartbeat_interval_seconds: "Heartbeat Interval Seconds",
  config_sync_interval_seconds: "Config Sync Interval",
  switch_probe_host: "Switch Host",
  switch_probe_port: "Switch Port",
  atm_cash_mode: "ATM Cash Mode",
  cash_provider: "Cash Provider",
  xfs_profile: "XFS Profile",
  xfs_logical_service: "XFS Logical Service",
  cash_layout: "Cash Layout",
  cash_read_interval_seconds: "Cash Read Interval",
  cash_stale_after_minutes: "Cash Stale After Minutes",
  recipient_email: "Recipient Email",
  sender_email: "Sender Email",
  smtp_host: "SMTP Host",
  smtp_port: "SMTP Port",
  smtp_security: "SMTP Security",
  smtp_username: "SMTP Username",
  whatsapp_gateway_url: "WhatsApp Gateway URL",
  whatsapp_default_recipient: "WhatsApp Recipient",
  whatsapp_default_recipients: "أرقام WhatsApp الافتراضية",
  whatsapp_numbers: "رقم WhatsApp المخصص",
  notify_whatsapp_disconnected: "WhatsApp Disconnect Alert",
  username: "اسم المستخدم",
  password: "كلمة المرور",
  file: "ملف ZIP",
  version: "رقم الإصدار",
  notes: "الملاحظات",
  atm_ids: "الصرافات المستهدفة",
};

function extractFieldName(location = []) {
  return location.filter((part) => !["body", "query", "path"].includes(part)).join(".");
}

function translatePlainMessage(message, status) {
  if (message?.startsWith("Value error, Path must be under C:\\ATM\\")) {
    return "المسار يجب أن يكون داخل C:\\ATM\\ مثل C:\\ATM\\Media.";
  }
  if (message?.startsWith("Unsupported file extension in ZIP:")) {
    return `يوجد ملف غير مسموح داخل ZIP: ${message.split(":").slice(1).join(":").trim()}`;
  }
  if (message?.startsWith("Unsafe path in ZIP member:")) {
    return `يوجد مسار غير آمن داخل ZIP: ${message.split(":").slice(1).join(":").trim()}`;
  }

  const known = {
    "Invalid username or password": "اسم المستخدم أو كلمة المرور غير صحيحة.",
    "Missing bearer token": "انتهت الجلسة أو لم يتم تسجيل الدخول.",
    "Invalid token": "جلسة الدخول غير صالحة. سجّل الدخول مرة أخرى.",
    "ATM ID already exists": "ATM ID مستخدم مسبقاً.",
    "Username already exists": "اسم المستخدم مستخدم مسبقاً.",
    "Admin access required": "هذه الصفحة تتطلب صلاحية مدير.",
    "Cannot deactivate yourself": "لا يمكنك تعطيل حسابك الحالي.",
    "Cannot remove admin role from yourself": "لا يمكنك إزالة صلاحية المدير من حسابك الحالي.",
    "Cannot deactivate the last active admin": "لا يمكن تعطيل آخر مدير نشط.",
    "Cannot remove the last active admin": "لا يمكن إزالة آخر مدير نشط.",
    "User not found": "المستخدم غير موجود.",
    "Package version already exists": "رقم الإصدار مستخدم مسبقاً. اختر رقم إصدار جديد أو اترك الحقل فارغاً ليتم توليده تلقائياً.",
    "ATM not found": "الصراف غير موجود.",
    "ATM already has a pending reboot request": "يوجد طلب إعادة تشغيل معلق لهذا الصراف بالفعل.",
    "Package not found": "حزمة التحديث غير موجودة.",
    "Only ZIP packages are accepted": "يجب رفع ملف ZIP فقط.",
    "Invalid ZIP file": "ملف ZIP غير صالح.",
    "ZIP package must contain at least one image file": "ملف ZIP يجب أن يحتوي على صورة واحدة على الأقل.",
    "atm-agent.exe is not available. Build it on Windows and place it at agent/dist/atm-agent.exe":
      "ملف atm-agent.exe غير متوفر على السيرفر. ابنِ الملف على Windows ثم ضعه في agent/dist/atm-agent.exe.",
    "Notification email settings are incomplete": "إعدادات البريد غير مكتملة.",
    "Notification default recipient email is missing": "أدخل بريدًا افتراضيًا لإرسال رسالة الاختبار.",
    "WhatsApp gateway settings are incomplete": "إعدادات WhatsApp غير مكتملة.",
    "Notification default WhatsApp recipient is missing": "أدخل رقم WhatsApp افتراضيًا لإرسال رسالة الاختبار.",
  };

  if (message?.startsWith("Executable or script file is not allowed in ZIP:")) {
    return `يوجد ملف تنفيذي أو سكربت ممنوع داخل ZIP: ${message.split(":").slice(1).join(":").trim()}`;
  }

  if (known[message]) return known[message];
  if (status === 401) return "غير مصرح. سجّل الدخول مرة أخرى.";
  if (status === 403) return "ليست لديك صلاحية لتنفيذ هذه العملية.";
  if (status === 404 && message?.toLowerCase?.().includes("whatsapp")) return "مسار WhatsApp غير متاح على السيرفر. حدّث السيرفر إلى آخر نسخة.";
  if (status === 404) return "العنصر المطلوب غير موجود.";
  if (status === 409) return "توجد بيانات مكررة أو تعارض في العملية.";
  if (status >= 500) return "حدث خطأ في الخادم. حاول مرة أخرى أو راجع السجلات.";
  return message || "تعذر تنفيذ الطلب.";
}

function formatValidationItem(item) {
  const fieldName = extractFieldName(item.loc);
  const label = fieldLabels[fieldName] || fieldName || "الحقل";
  const type = item.type || "";
  const ctx = item.ctx || {};

  if (type === "missing") return `${label}: هذا الحقل مطلوب.`;
  if (type === "string_too_short") return `${label}: يجب أن يحتوي على ${ctx.min_length || 2} أحرف على الأقل.`;
  if (type === "string_too_long") return `${label}: يجب ألا يتجاوز ${ctx.max_length} حرفاً.`;
  if (type === "list_too_short") return `${label}: اختر عنصراً واحداً على الأقل.`;
  if (type.includes("int")) return `${label}: يجب إدخال رقم صحيح.`;
  if (type.includes("literal")) return `${label}: القيمة غير مدعومة.`;

  return `${label}: ${item.msg || "قيمة غير صالحة."}`;
}

function parseErrorPayload(payload, status) {
  if (Array.isArray(payload?.detail)) {
    const details = payload.detail.map(formatValidationItem);
    const fieldErrors = {};

    payload.detail.forEach((item) => {
      const fieldName = extractFieldName(item.loc);
      if (fieldName) fieldErrors[fieldName] = formatValidationItem(item);
    });

    return {
      message: "يرجى تصحيح الحقول المحددة.",
      fieldErrors,
      details,
    };
  }

  if (typeof payload?.detail === "string") {
    return {
      message: translatePlainMessage(payload.detail, status),
      fieldErrors: {},
      details: [],
    };
  }

  if (payload?.detail?.missing_atm_ids) {
    return {
      message: `الصرافات التالية غير موجودة: ${payload.detail.missing_atm_ids.join(", ")}`,
      fieldErrors: {},
      details: [],
    };
  }

  if (payload?.detail?.message === "ATM has active updates") {
    return {
      message: `يوجد ${payload.detail.active_update_count} تحديث نشط مرتبط بهذا الصراف.`,
      fieldErrors: {},
      details: [],
    };
  }

  return {
    message: translatePlainMessage(null, status),
    fieldErrors: {},
    details: [],
  };
}

async function request(path, options = {}) {
  const token = getAuthToken();
  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch (err) {
    throw new ApiError(`تعذر الاتصال بالخادم: ${API_BASE}. تحقق من الشبكة أو المنفذ 8001.`, 0, null);
  }

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const parsed = parseErrorPayload(payload, response.status);
    if (response.status === 404 && path.includes("/whatsapp/")) {
      throw new ApiError("مسار WhatsApp غير متاح على السيرفر. حدّث السيرفر إلى آخر نسخة.", response.status, payload, {}, []);
    }
    throw new ApiError(parsed.message, response.status, payload, parsed.fieldErrors, parsed.details);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function downloadBlob(path) {
  const token = getAuthToken();
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (err) {
    throw new ApiError(`تعذر الاتصال بالخادم: ${API_BASE}. تحقق من الشبكة أو المنفذ 8001.`, 0, null);
  }

  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const parsed = parseErrorPayload(payload, response.status);
    throw new ApiError(parsed.message, response.status, payload, parsed.fieldErrors, parsed.details);
  }

  return response.blob();
}

export const api = {
  login: (payload) => request("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  me: () => request("/api/auth/me"),
  listUsers: () => request("/api/users"),
  listUserPages: () => request("/api/users/pages"),
  createUser: (payload) => request("/api/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (userId, payload) =>
    request(`/api/users/${encodeURIComponent(userId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (userId) => request(`/api/users/${encodeURIComponent(userId)}`, { method: "DELETE" }),
  listAtms: () => request("/api/atms"),
  createAtm: (payload) => request("/api/atms", { method: "POST", body: JSON.stringify(payload) }),
  getAtmDiagnostics: (atmId) => request(`/api/atms/${encodeURIComponent(atmId)}/diagnostics`),
  getAtmEvents: (atmId, limit = 80) =>
    request(`/api/atms/${encodeURIComponent(atmId)}/events?limit=${encodeURIComponent(limit)}`),
  updateAtm: (atmId, payload) =>
    request(`/api/atms/${encodeURIComponent(atmId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  regenerateAtmApiKey: (atmId) =>
    request(`/api/atms/${encodeURIComponent(atmId)}/regenerate-api-key`, { method: "POST" }),
  requestSwitchProbe: (atmId, payload = null) =>
    request(`/api/atms/${encodeURIComponent(atmId)}/switch-probe`, {
      method: "POST",
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    }),
  listSwitchProbes: (atmId) => request(`/api/atms/${encodeURIComponent(atmId)}/switch-probes`),
  deleteAtm: (atmId, force = false) =>
    request(`/api/atms/${encodeURIComponent(atmId)}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  getCashSummary: () => request("/api/cash/summary"),
  getCashAtm: (atmId) => request(`/api/cash/atms/${encodeURIComponent(atmId)}`),
  requestCashReadNow: (atmId) => request(`/api/cash/atms/${encodeURIComponent(atmId)}/read-now`, { method: "POST" }),
  getCashReport: () => request("/api/cash/reports/overview"),
  listCashAlerts: () => request("/api/cash/alerts"),
  saveCashThreshold: (payload) =>
    request("/api/cash/thresholds", { method: "POST", body: JSON.stringify(payload) }),
  getNotificationSettings: () => request("/api/notifications/settings"),
  updateNotificationSettings: (payload) =>
    request("/api/notifications/settings", { method: "PUT", body: JSON.stringify(payload) }),
  listNotificationRecipients: () => request("/api/notifications/recipients"),
  updateNotificationRecipients: (recipients) =>
    request("/api/notifications/recipients", { method: "PUT", body: JSON.stringify({ recipients }) }),
  sendTestNotification: () => request("/api/notifications/test", { method: "POST" }),
  getWhatsappStatus: () => request("/api/notifications/whatsapp/status"),
  getWhatsappQr: () => request("/api/notifications/whatsapp/qr"),
  sendWhatsAppTestNotification: () => request("/api/notifications/whatsapp/test", { method: "POST" }),
  listNotificationDeliveries: () => request("/api/notifications/deliveries"),
  listPackages: () => request("/api/packages"),
  getPackage: (id) => request(`/api/packages/${id}`),
  uploadPackage: (formData) => request("/api/packages/upload", { method: "POST", body: formData }),
  assignPackage: (id, atmIds) =>
    request(`/api/packages/${id}/assign`, { method: "POST", body: JSON.stringify({ atm_ids: atmIds }) }),
  retryFailedPackage: (id) => request(`/api/packages/${id}/retry-failed`, { method: "POST" }),
  downloadAgentSource: () => downloadBlob("/api/agent-downloads/source"),
  downloadAgentExe: () => downloadBlob("/api/agent-downloads/exe"),
  listLogs: () => request("/api/logs?limit=200"),
  listAuditLogs: () => request("/api/logs/audit?limit=200"),
};
