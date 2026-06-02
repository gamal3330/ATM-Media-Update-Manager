import { Download, FileArchive, Terminal } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";

export default function AgentDownloads() {
  const [downloading, setDownloading] = useState(false);
  const [downloadingExe, setDownloadingExe] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

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

  async function downloadSource() {
    setDownloading(true);
    setMessage("");
    setError("");
    try {
      const blob = await api.downloadAgentSource();
      saveBlob(blob, "ATM-Agent-Build-Source.zip");
      setMessage("تم تنزيل حزمة بناء Agent.");
    } catch (err) {
      setError(err.message || "تعذر تنزيل حزمة Agent");
    } finally {
      setDownloading(false);
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

  return (
    <section>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-slate-950">Agent Downloads</h1>
        <p className="text-sm text-slate-500">تحميل ملفات بناء Agent وتعليمات تثبيته كخدمة Windows</p>
      </div>
      {message && <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</div>}
      {error && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-5">
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold text-slate-950">
                <Download size={18} />
                <span>atm-agent.exe</span>
              </div>
            </div>
            <div className="p-4">
              <p className="mb-4 text-sm text-slate-600">
                استخدم هذا الزر من داخل الصراف لتنزيل ملف الـ Agent النهائي إذا كان مبنياً وموجوداً على السيرفر.
              </p>
              <button
                onClick={downloadExe}
                disabled={downloadingExe}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
                title="تنزيل atm-agent.exe"
              >
                <Download size={17} />
                <span>{downloadingExe ? "جار التنزيل..." : "Download atm-agent.exe"}</span>
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-4 py-3">
              <div className="flex items-center gap-2 font-semibold text-slate-950">
                <FileArchive size={18} />
                <span>ATM-Agent-Build-Source.zip</span>
              </div>
            </div>
            <div className="p-4">
              <p className="mb-4 text-sm text-slate-600">
                هذه الحزمة تُستخدم على جهاز بناء Windows لإنتاج ملف واحد `atm-agent.exe`. الصراف لا يحتاج Python بعد بناء الملف.
              </p>
              <button
                onClick={downloadSource}
                disabled={downloading}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
                title="تنزيل حزمة Agent"
              >
                <Download size={17} />
                <span>{downloading ? "جار التنزيل..." : "Download Agent Source"}</span>
              </button>
            </div>
          </div>
        </div>

        <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="flex items-center gap-2 font-semibold text-slate-950">
              <Terminal size={18} />
              <span>خطوات سريعة</span>
            </div>
          </div>
          <div className="space-y-4 p-4 text-sm text-slate-700">
            <div>
              <div className="mb-1 font-medium text-slate-950">1. على جهاز بناء Windows</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-white" dir="ltr">{`Expand-Archive .\\ATM-Agent-Build-Source.zip -DestinationPath .\\ATM-Agent
cd .\\ATM-Agent
.\\build_agent.bat`}</pre>
            </div>
            <div>
              <div className="mb-1 font-medium text-slate-950">2. ضع الناتج على السيرفر</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-white" dir="ltr">{`agent\\dist\\atm-agent.exe`}</pre>
            </div>
            <div>
              <div className="mb-1 font-medium text-slate-950">3. من داخل الصراف</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-white" dir="ltr">{`dist\\atm-agent.exe`}</pre>
            </div>
            <div>
              <div className="mb-1 font-medium text-slate-950">4. على الصراف كمسؤول</div>
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs text-white" dir="ltr">{`atm-agent.exe install --server-url="http://SERVER:8001" --atm-id="ATM001" --api-key="KEY"`}</pre>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
