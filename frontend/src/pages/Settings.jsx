import {
  Activity,
  CheckCircle2,
  Clipboard,
  Database,
  Download,
  FileArchive,
  KeyRound,
  Lock,
  RefreshCw,
  Server,
  Settings as SettingsIcon,
  ShieldCheck,
  Terminal,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, apiBaseUrl } from "../api/client";

const expectedAgentVersion = "2.0.0";
const onlineThresholdMinutes = 5;
const allowedExtensions = ["jpg", "jpeg", "png", "bmp", "gif"];
const blockedExtensions = ["exe", "ps1", "bat", "cmd", "vbs", "js", "jse", "msi", "dll", "scr", "com", "reg"];

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

export default function Settings({ onOpenAgentDownloads }) {
  const [health, setHealth] = useState({ status: "unknown", message: "لم يتم الفحص بعد", checkedAt: "" });
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [downloadingSource, setDownloadingSource] = useState(false);
  const [downloadingExe, setDownloadingExe] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const healthUrl = `${apiBaseUrl}/api/health`;
  const openedFrom = typeof window === "undefined" ? "-" : window.location.origin;
  const serviceCommand = `sc.exe query ATMUnifiedAgent`;
  const statusCommand = `"C:\\Program Files\\ATM Media Agent\\atm-agent.exe" status`;
  const healthCommand = `curl.exe ${healthUrl}`;

  const healthOk = health.status === "ok";
  const environmentRows = useMemo(
    () => [
      ["Frontend URL", openedFrom],
      ["API URL", apiBaseUrl],
      ["Health URL", healthUrl],
      ["Database", "SQLite"],
      ["Expected Agent", expectedAgentVersion],
      ["Online Threshold", `${onlineThresholdMinutes} minutes`],
    ],
    [healthUrl, openedFrom],
  );

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

  async function copyCommand(text, label) {
    setMessage("");
    setError("");
    try {
      await copyText(text);
      setMessage(`تم نسخ ${label}.`);
    } catch {
      setError(`تعذر نسخ ${label}.`);
    }
  }

  useEffect(() => {
    checkHealth();
  }, []);

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

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">
              <Server size={18} />
              <span>Environment</span>
            </div>
            <dl className="divide-y divide-slate-100 text-sm">
              {environmentRows.map(([label, value]) => (
                <div key={label} className="grid gap-2 px-4 py-3 md:grid-cols-[180px_minmax(0,1fr)]">
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="break-all font-mono text-slate-950" dir="ltr">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">
              <ShieldCheck size={18} />
              <span>Agent / Security Summary</span>
            </div>
            <div className="grid gap-3 p-4 md:grid-cols-2">
              {[
                [KeyRound, "API Key per ATM", "كل صراف يستخدم مفتاح مستقل، والمفتاح محفوظ كـ hash في السيرفر."],
                [Lock, "Pull Only", "الـ Agent هو من يتصل بالسيرفر، ولا يوجد دخول مباشر من السيرفر للصراف."],
                [FileArchive, "Image ZIP Only", `المسموح: ${allowedExtensions.join(", ")}`],
                [XCircle, "Blocked Executables", `الممنوع: ${blockedExtensions.join(", ")}`],
              ].map(([Icon, title, description]) => (
                <div key={title} className="rounded-lg bg-slate-50 px-3 py-3">
                  <div className="mb-2 flex items-center gap-2 font-medium text-slate-950">
                    <Icon size={17} />
                    <span>{title}</span>
                  </div>
                  <p className="text-sm text-slate-600">{description}</p>
                </div>
              ))}
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

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">
              <Terminal size={18} />
              <span>Commands</span>
            </div>
            <div className="space-y-4 p-4 text-sm">
              {[
                ["Health Check", healthCommand],
                ["Service Status", serviceCommand],
                ["Agent Status", statusCommand],
              ].map(([label, command]) => (
                <div key={label}>
                  <div className="mb-1 flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-950">{label}</span>
                    <button
                      onClick={() => copyCommand(command, label)}
                      className="focus-ring inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                      title={`نسخ ${label}`}
                    >
                      <Clipboard size={13} />
                      <span>Copy</span>
                    </button>
                  </div>
                  <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-white" dir="ltr">{command}</pre>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">
              <Database size={18} />
              <span>Storage</span>
            </div>
            <div className="space-y-2 p-4 text-sm text-slate-700">
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-500">Database</span>
                <span className="font-medium text-slate-950">SQLite MVP</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-500">Package Storage</span>
                <span className="font-medium text-slate-950">backend/uploads</span>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
