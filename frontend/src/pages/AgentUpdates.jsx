import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Cpu,
  FileUp,
  HardDriveDownload,
  PackageCheck,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  Square,
  SquareCheck,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";

const statusStyles = {
  applied: "bg-emerald-50 text-emerald-700",
  failed: "bg-rose-50 text-rose-700",
  pending: "bg-amber-50 text-amber-700",
  downloading: "bg-sky-50 text-sky-700",
  applying: "bg-indigo-50 text-indigo-700",
  unassigned: "bg-slate-100 text-slate-600",
};

const statusLabels = {
  applied: "تم التحديث",
  failed: "فشل",
  pending: "ينتظر السحب",
  downloading: "جاري التنزيل",
  applying: "جاري التطبيق",
  unassigned: "غير معين",
};

const phaseLabels = {
  pending: "بانتظار الـ Agent",
  downloading: "تنزيل الملفات",
  applying: "تشغيل updater",
  applied: "اكتمل",
  failed: "فشل",
};

const progressMessageLabels = {
  "Agent update is ready for download": "تحديث الـ Agent جاهز للسحب",
  "Agent update download started": "بدأ تنزيل تحديث الـ Agent",
  "agent download started": "بدأ تنزيل atm-agent.exe",
  "updater download started": "بدأ تنزيل agent-updater.exe",
  "atm-agent.exe downloaded": "تم تنزيل atm-agent.exe",
  "agent-updater.exe downloaded": "تم تنزيل agent-updater.exe",
  "Agent updater launched": "تم تشغيل أداة التحديث",
  "Agent update applied": "تم تحديث الـ Agent",
  "Agent is already running the requested version": "الصراف يعمل بهذه النسخة مسبقاً",
};

function translateProgressMessage(message) {
  return progressMessageLabels[message] || message || "";
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let size = number;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function targetMap(details) {
  const map = new Map();
  details?.targets?.forEach((target) => map.set(target.atm.atm_id, target));
  return map;
}

function canSelectAtm(target) {
  if (!target) return true;
  return target.status === "failed";
}

function countsFromDetails(details, fallback) {
  const counts = {
    total: fallback?.total_targets || 0,
    pending: fallback?.pending_targets || 0,
    applied: fallback?.applied_targets || 0,
    failed: fallback?.failed_targets || 0,
    downloading: 0,
    applying: 0,
  };
  if (!details?.targets) return counts;
  const next = { total: 0, pending: 0, applied: 0, failed: 0, downloading: 0, applying: 0 };
  details.targets.forEach((target) => {
    next.total += 1;
    if (target.status === "pending") next.pending += 1;
    if (target.status === "downloading") next.downloading += 1;
    if (target.status === "applying") next.applying += 1;
    if (target.status === "applied") next.applied += 1;
    if (target.status === "failed") next.failed += 1;
  });
  return next;
}

function ProgressBar({ target }) {
  const percent = Math.max(0, Math.min(100, Number(target?.progress_percent || 0)));
  const status = target?.status || "pending";
  const phase = phaseLabels[target?.progress_phase] || phaseLabels[status] || status;
  const message = translateProgressMessage(target?.progress_message);
  const barColor =
    status === "failed"
      ? "bg-rose-600"
      : status === "applied"
        ? "bg-emerald-600"
        : status === "applying"
          ? "bg-indigo-600"
          : "bg-teal-600";

  return (
    <div className="min-w-[220px]">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span className="truncate">{phase}</span>
        <span dir="ltr">{percent}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${percent}%` }} />
      </div>
      {message && <div className="mt-1 truncate text-xs text-slate-500">{message}</div>}
    </div>
  );
}

function FilePicker({ label, value, onChange, accept = ".exe" }) {
  const inputRef = useRef(null);
  const fileName = value?.name || "لم يتم اختيار ملف";

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-900">{label}</div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          title={`اختيار ${label}`}
        >
          <FileUp size={16} />
          <span>اختيار</span>
        </button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
      <div className="truncate text-sm text-slate-500" dir="ltr" title={fileName}>
        {fileName}
      </div>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, tone = "slate" }) {
  const toneClass = {
    slate: "bg-white text-slate-900 border-slate-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    rose: "bg-rose-50 text-rose-800 border-rose-200",
    sky: "bg-sky-50 text-sky-800 border-sky-200",
  }[tone];
  return (
    <div className={`rounded-lg border px-4 py-3 ${toneClass}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium opacity-80">{label}</div>
        <Icon size={18} className="opacity-70" />
      </div>
      <div className="mt-2 text-2xl font-semibold" dir="ltr">
        {value}
      </div>
    </div>
  );
}

export default function AgentUpdates({ atms = [] }) {
  const [packages, setPackages] = useState([]);
  const [selectedPackageId, setSelectedPackageId] = useState(null);
  const [details, setDetails] = useState(null);
  const [selectedAtms, setSelectedAtms] = useState([]);
  const [uploadForm, setUploadForm] = useState({ version: "", notes: "", agentFile: null, updaterFile: null });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const selectedPackage = useMemo(
    () => packages.find((item) => item.id === selectedPackageId) || null,
    [packages, selectedPackageId],
  );
  const detailsLoaded = Boolean(details && details.id === selectedPackageId);
  const counts = useMemo(() => countsFromDetails(detailsLoaded ? details : null, selectedPackage), [details, detailsLoaded, selectedPackage]);
  const targetsByAtmId = useMemo(() => targetMap(detailsLoaded ? details : null), [details, detailsLoaded]);
  const assignableAtms = useMemo(
    () => (detailsLoaded ? atms.filter((atm) => canSelectAtm(targetsByAtmId.get(atm.atm_id))) : []),
    [atms, detailsLoaded, targetsByAtmId],
  );
  const activeTargets = useMemo(
    () => (detailsLoaded ? details?.targets?.some((target) => ["pending", "downloading", "applying"].includes(target.status)) || false : false),
    [details, detailsLoaded],
  );

  async function loadPackages(nextSelectedId = selectedPackageId, { loadSelectedDetails = false } = {}) {
    setLoading(true);
    setError("");
    try {
      const data = await api.listAgentPackages({ limit: 50 });
      setPackages(data);
      const nextId = nextSelectedId || data[0]?.id || null;
      setSelectedPackageId(nextId);
      if (nextId && loadSelectedDetails) {
        setDetails(await api.getAgentPackage(nextId));
      } else {
        setDetails(null);
      }
    } catch (err) {
      setError(err.message || "تعذر تحميل تحديثات Agent");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetails(packageId = selectedPackageId) {
    if (!packageId) return;
    setError("");
    try {
      setDetails(await api.getAgentPackage(packageId));
    } catch (err) {
      setError(err.message || "تعذر تحميل تفاصيل تحديث Agent");
    }
  }

  useEffect(() => {
    loadPackages(null, { loadSelectedDetails: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedPackageId || !activeTargets) return undefined;
    const timer = window.setInterval(() => loadDetails(selectedPackageId), 10000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPackageId, activeTargets]);

  async function selectPackage(packageId) {
    setSelectedPackageId(packageId);
    setSelectedAtms([]);
    setMessage("");
    setError("");
    await loadDetails(packageId);
  }

  async function uploadPackage(event) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!uploadForm.version.trim()) {
      setError("أدخل رقم إصدار واضح، مثل 2.0.8.");
      return;
    }
    if (!uploadForm.agentFile || !uploadForm.updaterFile) {
      setError("اختر ملف atm-agent.exe وملف agent-updater.exe.");
      return;
    }

    const formData = new FormData();
    formData.append("version", uploadForm.version.trim());
    formData.append("notes", uploadForm.notes.trim());
    formData.append("agent_file", uploadForm.agentFile);
    formData.append("updater_file", uploadForm.updaterFile);

    setUploading(true);
    try {
      const created = await api.uploadAgentPackage(formData);
      setMessage(`تم رفع نسخة Agent ${created.version}.`);
      setUploadForm({ version: "", notes: "", agentFile: null, updaterFile: null });
      await loadPackages(created.id, { loadSelectedDetails: true });
    } catch (err) {
      setError(err.message || "فشل رفع نسخة Agent");
    } finally {
      setUploading(false);
    }
  }

  function toggleAtm(atmId) {
    setSelectedAtms((current) =>
      current.includes(atmId) ? current.filter((id) => id !== atmId) : [...current, atmId],
    );
  }

  async function assignSelected() {
    if (!selectedPackageId || selectedAtms.length === 0) return;
    setAssigning(true);
    setMessage("");
    setError("");
    try {
      const result = await api.assignAgentPackage(selectedPackageId, selectedAtms);
      setMessage(`تم إرسال التحديث إلى ${result.targets.length} صراف.`);
      setSelectedAtms([]);
      await loadPackages(selectedPackageId, { loadSelectedDetails: true });
    } catch (err) {
      setError(err.message || "فشل تعيين تحديث Agent");
    } finally {
      setAssigning(false);
    }
  }

  async function retryFailed() {
    if (!selectedPackageId || counts.failed === 0) return;
    setRetrying(true);
    setMessage("");
    setError("");
    try {
      const result = await api.retryFailedAgentPackage(selectedPackageId);
      setMessage(`تمت إعادة محاولة ${result.assigned} صراف.`);
      await loadPackages(selectedPackageId, { loadSelectedDetails: true });
    } catch (err) {
      setError(err.message || "تعذر إعادة محاولة التحديثات الفاشلة");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
            <PackageCheck size={28} />
            <span>تحديثات Agent المركزية</span>
          </h1>
          <p className="mt-1 text-sm text-slate-500">رفع نسخة Agent 32-bit وتوزيعها على الصرافات ومتابعة النتيجة</p>
        </div>
        <button
          onClick={() => loadPackages(selectedPackageId, { loadSelectedDetails: detailsLoaded })}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          title="تحديث"
        >
          <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          <span>تحديث</span>
        </button>
      </div>

      {(message || error) && (
        <div
          className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
            error ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          {error ? <AlertCircle className="mt-0.5 shrink-0" size={17} /> : <CheckCircle2 className="mt-0.5 shrink-0" size={17} />}
          <span>{error || message}</span>
        </div>
      )}

      <form onSubmit={uploadPackage} className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold text-slate-950">
            <UploadCloud size={19} />
            <span>رفع نسخة جديدة</span>
          </div>
        </div>
        <div className="grid gap-4 p-4 lg:grid-cols-[1fr_1fr_1.2fr]">
          <div className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">الإصدار</span>
              <input
                value={uploadForm.version}
                onChange={(event) => setUploadForm((current) => ({ ...current, version: event.target.value }))}
                placeholder="2.0.8"
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                dir="ltr"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">ملاحظات</span>
              <input
                value={uploadForm.notes}
                onChange={(event) => setUploadForm((current) => ({ ...current, notes: event.target.value }))}
                placeholder="اختياري"
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>
          <div className="space-y-3">
            <FilePicker
              label="atm-agent.exe"
              value={uploadForm.agentFile}
              onChange={(file) => setUploadForm((current) => ({ ...current, agentFile: file }))}
            />
            <FilePicker
              label="agent-updater.exe"
              value={uploadForm.updaterFile}
              onChange={(file) => setUploadForm((current) => ({ ...current, updaterFile: file }))}
            />
          </div>
          <div className="flex flex-col justify-between gap-3 rounded-lg bg-slate-50 p-3">
            <div className="space-y-2 text-sm text-slate-600">
              <div className="flex items-center gap-2 text-slate-900">
                <Cpu size={17} />
                <span className="font-semibold">التحقق قبل القبول</span>
              </div>
              <p>السيرفر يرفض أي ملف ليس Windows EXE أو ليس 32-bit x86.</p>
              <p>بعد التعيين، الـ Agent يتحقق من SHA256 قبل تشغيل updater.</p>
            </div>
            <button
              type="submit"
              disabled={uploading}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:opacity-60"
              title="حفظ نسخة Agent"
            >
              <Save size={17} />
              <span>{uploading ? "جاري الرفع..." : "حفظ النسخة"}</span>
            </button>
          </div>
        </div>
      </form>

      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">النسخ المرفوعة</div>
          <div className="max-h-[620px] overflow-auto">
            {packages.map((item) => {
              const selected = item.id === selectedPackageId;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectPackage(item.id)}
                  className={`block w-full border-b border-slate-100 px-4 py-3 text-right last:border-b-0 hover:bg-slate-50 ${
                    selected ? "bg-teal-50" : "bg-white"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-950">{item.version}</div>
                      <div className="mt-1 text-xs text-slate-500">{formatApiDate(item.created_at)}</div>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{item.architecture}</span>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <span className="rounded-lg bg-emerald-50 px-2 py-1 text-emerald-700">تم {item.applied_targets}</span>
                    <span className="rounded-lg bg-amber-50 px-2 py-1 text-amber-700">ينتظر {item.pending_targets}</span>
                    <span className="rounded-lg bg-rose-50 px-2 py-1 text-rose-700">فشل {item.failed_targets}</span>
                  </div>
                </button>
              );
            })}
            {packages.length === 0 && (
              <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد نسخ مرفوعة بعد</div>
            )}
          </div>
        </aside>

        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-5">
            <StatTile icon={HardDriveDownload} label="مستهدف" value={counts.total} />
            <StatTile icon={Clock3} label="ينتظر" value={counts.pending} tone="amber" />
            <StatTile icon={RefreshCw} label="جاري" value={counts.downloading + counts.applying} tone="sky" />
            <StatTile icon={CheckCircle2} label="تم" value={counts.applied} tone="emerald" />
            <StatTile icon={XCircle} label="فشل" value={counts.failed} tone="rose" />
          </div>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div>
                <div className="font-semibold text-slate-950">
                  {selectedPackage ? `نسخة ${selectedPackage.version}` : "اختر نسخة Agent"}
                </div>
                {selectedPackage && (
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                    <span>{selectedPackage.agent_original_filename}</span>
                    <span>{formatBytes(selectedPackage.agent_size_bytes)}</span>
                    <span>{selectedPackage.updater_original_filename}</span>
                    <span>{formatBytes(selectedPackage.updater_size_bytes)}</span>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setSelectedAtms(assignableAtms.map((atm) => atm.atm_id))}
                  disabled={!selectedPackageId || assignableAtms.length === 0}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                  title="اختيار المتاح"
                >
                  <SquareCheck size={16} />
                  <span>اختيار المتاح</span>
                </button>
                <button
                  onClick={() => setSelectedAtms([])}
                  disabled={selectedAtms.length === 0}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                  title="مسح الاختيار"
                >
                  <Square size={16} />
                  <span>مسح</span>
                </button>
                <button
                  onClick={retryFailed}
                  disabled={!selectedPackageId || counts.failed === 0 || retrying}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                  title="إعادة محاولة الفاشلة"
                >
                  <RotateCcw size={16} />
                  <span>{retrying ? "جاري..." : "Retry Failed"}</span>
                </button>
              </div>
            </div>

            <div className="grid gap-4 p-4 lg:grid-cols-[360px_1fr]">
              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium text-slate-900">اختيار الصرافات</div>
                    <div className="text-xs text-slate-500">
                      {selectedAtms.length} محدد من {assignableAtms.length} متاح
                    </div>
                  </div>
                  <button
                    onClick={assignSelected}
                    disabled={!selectedPackageId || selectedAtms.length === 0 || assigning}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-60"
                    title="إرسال التحديث"
                  >
                    <Send size={16} />
                    <span>{assigning ? "إرسال..." : "إرسال"}</span>
                  </button>
                </div>
                <div className="max-h-[480px] overflow-auto rounded-lg border border-slate-200">
                  {atms.map((atm) => {
                    const target = targetsByAtmId.get(atm.atm_id);
                    const status = target?.status || "unassigned";
                    const selectable = detailsLoaded && Boolean(selectedPackageId) && canSelectAtm(target);
                    const selected = selectedAtms.includes(atm.atm_id);
                    return (
                      <label
                        key={atm.atm_id}
                        className={`flex items-center gap-3 border-b border-slate-100 px-3 py-3 text-sm last:border-b-0 ${
                          selectable ? "cursor-pointer hover:bg-slate-50" : "cursor-not-allowed bg-slate-50/70"
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="h-4 w-4"
                          disabled={!selectable}
                          checked={selected}
                          onChange={() => toggleAtm(atm.atm_id)}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="truncate font-medium text-slate-950">{atm.name}</div>
                          <div className="truncate text-xs text-slate-500">
                            {atm.atm_id} · Agent {atm.agent_version || "-"}
                          </div>
                        </div>
                        <span className={`rounded-full px-2 py-1 text-xs ${statusStyles[status] || statusStyles.pending}`}>
                          {statusLabels[status] || status}
                        </span>
                      </label>
                    );
                  })}
                  {atms.length === 0 && (
                    <div className="px-3 py-8 text-center text-sm text-slate-500">لا توجد صرافات بعد</div>
                  )}
                </div>
              </div>

              <div className="min-w-0">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium text-slate-900">متابعة التنفيذ</div>
                    <div className="text-xs text-slate-500">يتم التحديث تلقائياً كل بضع ثوان عند وجود عمليات نشطة</div>
                  </div>
                  <button
                    onClick={() => loadDetails()}
                    disabled={!selectedPackageId}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                    title="تحديث التفاصيل"
                  >
                    <RefreshCw size={16} />
                    <span>تحديث</span>
                  </button>
                </div>
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="min-w-[860px] divide-y divide-slate-200 text-sm">
                    <thead className="bg-slate-50 text-slate-600">
                      <tr>
                        <th className="px-4 py-3 text-right font-medium">الصراف</th>
                        <th className="px-4 py-3 text-right font-medium">الحالة</th>
                        <th className="px-4 py-3 text-right font-medium">التقدم</th>
                        <th className="px-4 py-3 text-right font-medium">المحاولات</th>
                        <th className="px-4 py-3 text-right font-medium">آخر فحص</th>
                        <th className="px-4 py-3 text-right font-medium">الرسالة</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {detailsLoaded && details?.targets?.map((target) => (
                        <tr key={target.id}>
                          <td className="px-4 py-3">
                            <div className="font-medium text-slate-950">{target.atm.name}</div>
                            <div className="text-xs text-slate-500">{target.atm.atm_id}</div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`rounded-full px-2 py-1 text-xs ${statusStyles[target.status] || statusStyles.pending}`}>
                              {statusLabels[target.status] || target.status}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <ProgressBar target={target} />
                          </td>
                          <td className="px-4 py-3" dir="ltr">
                            {target.attempt_count}
                          </td>
                          <td className="px-4 py-3">{formatApiDate(target.last_checked_at)}</td>
                          <td className={`max-w-[320px] px-4 py-3 ${target.last_error ? "text-rose-700" : "text-slate-500"}`}>
                            <div className="truncate" title={target.last_error || translateProgressMessage(target.progress_message) || ""}>
                              {target.last_error || translateProgressMessage(target.progress_message) || "-"}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {selectedPackage && !detailsLoaded && (
                        <tr>
                          <td colSpan="6" className="px-4 py-10 text-center text-slate-500">
                            <button
                              type="button"
                              onClick={() => loadDetails()}
                              className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                            >
                              <RefreshCw size={16} />
                              <span>تحميل تفاصيل النسخة</span>
                            </button>
                          </td>
                        </tr>
                      )}
                      {detailsLoaded && (!details?.targets || details.targets.length === 0) && (
                        <tr>
                          <td colSpan="6" className="px-4 py-10 text-center text-slate-500">
                            لا توجد صرافات مستهدفة لهذه النسخة بعد
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
