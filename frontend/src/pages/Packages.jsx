import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Eye,
  RefreshCw,
  RotateCcw,
  Send,
  Square,
  SquareCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";

const statusStyles = {
  applied: "bg-emerald-50 text-emerald-700",
  failed: "bg-rose-50 text-rose-700",
  pending: "bg-amber-50 text-amber-700",
  downloading: "bg-sky-50 text-sky-700",
  unassigned: "bg-slate-100 text-slate-600",
};

const statusLabels = {
  applied: "تم التطبيق",
  failed: "فشل",
  pending: "ينتظر السحب",
  downloading: "قيد التنزيل",
  unassigned: "غير معيّن",
};

const phaseLabels = {
  pending: "بانتظار السحب",
  downloading: "تنزيل الحزمة",
  applying: "تطبيق الملفات",
  rollback: "استرجاع النسخة",
  applied: "اكتمل",
  failed: "فشل",
};

const progressMessageLabels = {
  "Update is ready for download": "التحديث جاهز للسحب",
  "Download started": "بدأ تنزيل الحزمة",
  "Downloading package": "جار تنزيل الحزمة",
  "Download completed": "اكتمل تنزيل الحزمة",
  "Checksum verified": "تم التحقق من SHA256",
  "Extracting package": "جار فك ضغط الحزمة",
  "Package extracted": "تم فك ضغط الحزمة",
  "Creating backup": "جار أخذ نسخة احتياطية",
  "Copying media files": "جار نسخ ملفات الصور",
  "Media files copied": "تم نسخ ملفات الصور",
  "Rollback started": "بدأ استرجاع النسخة الاحتياطية",
};

function translateProgressMessage(message) {
  return progressMessageLabels[message] || message;
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function TargetProgress({ target, compact = false }) {
  if (!target) return null;
  const percent = Math.max(0, Math.min(100, target.progress_percent || 0));
  const phase = phaseLabels[target.progress_phase] || phaseLabels[target.status] || target.progress_phase || target.status;
  const message = translateProgressMessage(target.progress_message);
  const hasBytes = Number.isFinite(target.bytes_downloaded) && Number.isFinite(target.total_bytes) && target.total_bytes > 0;
  const bytesText = hasBytes ? `${formatBytes(target.bytes_downloaded)} / ${formatBytes(target.total_bytes)}` : "";
  const barColor =
    target.status === "failed"
      ? "bg-rose-600"
      : target.status === "applied"
        ? "bg-emerald-600"
        : "bg-teal-600";

  return (
    <div className={compact ? "mt-2" : "min-w-[220px]"}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span className="truncate">{phase}</span>
        <span dir="ltr">{percent}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${percent}%` }} />
      </div>
      {!compact && (message || bytesText) && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
          {message && <span className="truncate">{message}</span>}
          {bytesText && <span dir="ltr">{bytesText}</span>}
        </div>
      )}
    </div>
  );
}

function getTargetByAtmId(details) {
  const map = new Map();
  details?.targets?.forEach((target) => map.set(target.atm.atm_id, target));
  return map;
}

function canSelectAtm(target) {
  if (!target) return true;
  return target.status === "failed";
}

function getAssignmentKind(target) {
  if (!target) return "new";
  if (target.status === "failed") return "retry";
  return "locked";
}

export default function Packages({ packages, atms, onChanged }) {
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [activeTab, setActiveTab] = useState("assign");
  const [selectedAtms, setSelectedAtms] = useState([]);
  const [details, setDetails] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [retryingFailed, setRetryingFailed] = useState(false);

  const selectedPackageData = useMemo(
    () => packages.find((item) => item.id === selectedPackage),
    [packages, selectedPackage],
  );

  const targetByAtmId = useMemo(() => getTargetByAtmId(details), [details]);

  const assignableAtms = useMemo(
    () => atms.filter((atm) => canSelectAtm(targetByAtmId.get(atm.atm_id))),
    [atms, targetByAtmId],
  );

  const selectedSummary = useMemo(() => {
    let newTargets = 0;
    let retries = 0;
    selectedAtms.forEach((atmId) => {
      const kind = getAssignmentKind(targetByAtmId.get(atmId));
      if (kind === "new") newTargets += 1;
      if (kind === "retry") retries += 1;
    });
    return { newTargets, retries };
  }, [selectedAtms, targetByAtmId]);

  const hasActiveTargets = useMemo(
    () => details?.targets?.some((target) => ["pending", "downloading"].includes(target.status)) || false,
    [details],
  );

  const detailCounts = useMemo(() => {
    const counts = { total: 0, pending: 0, downloading: 0, applied: 0, failed: 0 };
    details?.targets?.forEach((target) => {
      counts.total += 1;
      if (target.status === "pending") counts.pending += 1;
      if (target.status === "downloading") counts.downloading += 1;
      if (target.status === "applied") counts.applied += 1;
      if (target.status === "failed") counts.failed += 1;
    });
    return counts;
  }, [details]);

  useEffect(() => {
    if (!selectedPackage && packages.length > 0) {
      setSelectedPackage(packages[0].id);
    }
  }, [packages, selectedPackage]);

  useEffect(() => {
    setSelectedAtms([]);
    setMessage("");
    setError("");

    if (!selectedPackage) {
      setDetails(null);
      return;
    }

    setLoadingDetails(true);
    api
      .getPackage(selectedPackage)
      .then(setDetails)
      .catch((err) => setError(err.message || "تعذر تحميل تفاصيل الحزمة"))
      .finally(() => setLoadingDetails(false));
  }, [selectedPackage]);

  useEffect(() => {
    if (!selectedPackage || !hasActiveTargets) return undefined;

    const intervalId = window.setInterval(async () => {
      try {
        const nextDetails = await api.getPackage(selectedPackage);
        setDetails(nextDetails);
        if (nextDetails.targets?.some((target) => ["pending", "downloading"].includes(target.status))) {
          onChanged();
        }
      } catch {
        // Keep the current view stable; the manual refresh/global error path handles persistent issues.
      }
    }, 3000);

    return () => window.clearInterval(intervalId);
  }, [selectedPackage, hasActiveTargets, onChanged]);

  function toggleAtm(atmId) {
    setSelectedAtms((current) =>
      current.includes(atmId) ? current.filter((id) => id !== atmId) : [...current, atmId],
    );
  }

  function selectAllAssignable() {
    setSelectedAtms(assignableAtms.map((atm) => atm.atm_id));
  }

  async function assign() {
    if (!selectedPackage || selectedAtms.length === 0) return;
    setError("");
    setMessage("");
    setAssigning(true);
    try {
      await api.assignPackage(selectedPackage, selectedAtms);
      const parts = [];
      if (selectedSummary.newTargets > 0) parts.push(`${selectedSummary.newTargets} تعيين جديد`);
      if (selectedSummary.retries > 0) parts.push(`${selectedSummary.retries} إعادة محاولة`);
      setMessage(parts.length ? `تم إرسال ${parts.join(" و ")}.` : "لا توجد تغييرات جديدة لهذه الحزمة.");
      setSelectedAtms([]);
      onChanged();
      setDetails(await api.getPackage(selectedPackage));
    } catch (err) {
      setError(err.message || "فشل التعيين");
    } finally {
      setAssigning(false);
    }
  }

  async function refreshDetails() {
    if (!selectedPackage) return;
    setLoadingDetails(true);
    setError("");
    try {
      setDetails(await api.getPackage(selectedPackage));
      onChanged();
    } catch (err) {
      setError(err.message || "تعذر تحديث تفاصيل الحزمة");
    } finally {
      setLoadingDetails(false);
    }
  }

  async function retryFailed() {
    if (!selectedPackage || detailCounts.failed === 0) return;
    const confirmed = window.confirm(`سيتم إعادة محاولة ${detailCounts.failed} صراف فشل في هذه الحزمة. هل تريد المتابعة؟`);
    if (!confirmed) return;

    setRetryingFailed(true);
    setError("");
    setMessage("");
    try {
      const result = await api.retryFailedPackage(selectedPackage);
      setMessage(`تمت إعادة محاولة ${result.assigned} صراف فاشل.`);
      setSelectedAtms([]);
      onChanged();
      setDetails(await api.getPackage(selectedPackage));
    } catch (err) {
      setError(err.message || "تعذر إعادة المحاولة");
    } finally {
      setRetryingFailed(false);
    }
  }

  return (
    <section>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-slate-950">تفاصيل التحديثات</h1>
        <p className="text-sm text-slate-500">اختيار الحزمة وتحديد الصرافات المستهدفة ومتابعة التنفيذ</p>
      </div>

      <div className="mb-5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">الحزم المتاحة</div>
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-right font-medium">الإصدار</th>
              <th className="px-4 py-3 text-right font-medium">الملف</th>
              <th className="px-4 py-3 text-right font-medium">التقدم</th>
              <th className="px-4 py-3 text-right font-medium">اختيار</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {packages.map((item) => {
              const selected = item.id === selectedPackage;
              return (
                <tr key={item.id} className={selected ? "bg-teal-50/70" : ""}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{item.version}</div>
                    <div className="text-xs text-slate-500">{formatApiDate(item.created_at)}</div>
                  </td>
                  <td className="px-4 py-3">{item.original_filename}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700">
                        {item.applied_targets} تم
                      </span>
                      <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">
                        {item.pending_targets} ينتظر
                      </span>
                      <span className="rounded-full bg-rose-50 px-2 py-1 text-xs text-rose-700">
                        {item.failed_targets} فشل
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setSelectedPackage(item.id)}
                      className={`focus-ring inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${
                        selected
                          ? "border-teal-600 bg-teal-700 text-white"
                          : "border-slate-300 bg-white hover:bg-slate-50"
                      }`}
                      title="اختيار الحزمة"
                    >
                      <Eye size={16} />
                      <span>{selected ? "محددة" : "اختيار"}</span>
                    </button>
                  </td>
                </tr>
              );
            })}
            {packages.length === 0 && (
              <tr>
                <td colSpan="4" className="px-4 py-8 text-center text-slate-500">
                  لا توجد تحديثات بعد
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mb-5 inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
        <button
          type="button"
          onClick={() => setActiveTab("assign")}
          className={`focus-ring inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium ${
            activeTab === "assign" ? "bg-teal-700 text-white" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Send size={16} />
          <span>تعيين الحزمة</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("monitor")}
          className={`focus-ring inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium ${
            activeTab === "monitor" ? "bg-teal-700 text-white" : "text-slate-600 hover:bg-slate-50"
          }`}
        >
          <Clock3 size={16} />
          <span>متابعة التنفيذ</span>
        </button>
      </div>

      {activeTab === "assign" && (
        <>
          <div className="mb-5 grid gap-3 md:grid-cols-3">
            {[
              ["1", "اختر الحزمة", selectedPackageData?.version || "لا توجد حزمة"],
              ["2", "حدد الصرافات", `${selectedAtms.length} محدد`],
              ["3", "أرسل التعيين", assigning ? "جار الإرسال" : "جاهز"],
            ].map(([number, title, value]) => (
              <div key={number} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <div className="mb-2 flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-white">
                    {number}
                  </span>
                  <span className="font-medium text-slate-900">{title}</span>
                </div>
                <div className="truncate text-sm text-slate-500">{value}</div>
              </div>
            ))}
          </div>

          <aside className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-slate-950">تعيين الحزمة</h2>
                <p className="mt-1 text-sm text-slate-500">{selectedPackageData?.version || "اختر حزمة أولاً"}</p>
              </div>
              <button
                onClick={refreshDetails}
                disabled={!selectedPackage || loadingDetails}
                className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                title="تحديث التفاصيل"
              >
                <RefreshCw size={16} />
                <span>تحديث</span>
              </button>
            </div>
          </div>

          {selectedPackageData && (
            <div className="border-b border-slate-100 p-4">
              <div className="grid grid-cols-5 gap-2 text-sm">
                <div>
                  <div className="text-slate-500">مستهدف</div>
                  <div className="mt-1 font-semibold text-slate-900">{detailCounts.total || selectedPackageData.total_targets}</div>
                </div>
                <div>
                  <div className="text-slate-500">تم</div>
                  <div className="mt-1 font-semibold text-emerald-700">{detailCounts.applied || selectedPackageData.applied_targets}</div>
                </div>
                <div>
                  <div className="text-slate-500">ينتظر</div>
                  <div className="mt-1 font-semibold text-amber-700">{detailCounts.pending}</div>
                </div>
                <div>
                  <div className="text-slate-500">جاري</div>
                  <div className="mt-1 font-semibold text-sky-700">{detailCounts.downloading}</div>
                </div>
                <div>
                  <div className="text-slate-500">فشل</div>
                  <div className="mt-1 font-semibold text-rose-700">{detailCounts.failed || selectedPackageData.failed_targets}</div>
                </div>
              </div>
              <div className="mt-3 truncate font-mono text-xs text-slate-500" dir="ltr" title={selectedPackageData.sha256}>
                SHA256: {selectedPackageData.sha256}
              </div>
            </div>
          )}

          <div className="border-b border-slate-100 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="font-medium text-slate-900">الصرافات</div>
                <div className="text-xs text-slate-500">
                  {assignableAtms.length} قابل للتعيين من أصل {atms.length}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={retryFailed}
                  disabled={!selectedPackage || detailCounts.failed === 0 || retryingFailed}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                  title="إعادة محاولة الفاشلة"
                >
                  <RotateCcw size={16} />
                  <span>{retryingFailed ? "جار الإعادة" : "Retry Failed"}</span>
                </button>
                <button
                  onClick={selectAllAssignable}
                  disabled={!selectedPackage || assignableAtms.length === 0}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  title="اختيار القابلة للتعيين"
                >
                  <SquareCheck size={16} />
                  <span>اختيار المتاح</span>
                </button>
                <button
                  onClick={() => setSelectedAtms([])}
                  disabled={selectedAtms.length === 0}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  title="مسح الاختيار"
                >
                  <Square size={16} />
                  <span>مسح</span>
                </button>
              </div>
            </div>

            <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
              {loadingDetails && <div className="px-3 py-4 text-center text-sm text-slate-500">جار تحميل التفاصيل...</div>}
              {!loadingDetails &&
                atms.map((atm) => {
                  const target = targetByAtmId.get(atm.atm_id);
                  const status = target?.status || "unassigned";
                  const selectable = selectedPackage && canSelectAtm(target);
                  const selected = selectedAtms.includes(atm.atm_id);

                  return (
                    <label
                      key={atm.atm_id}
                      className={`flex items-center gap-3 border-b border-slate-100 px-3 py-3 text-sm last:border-b-0 ${
                        selectable ? "cursor-pointer hover:bg-slate-50" : "cursor-not-allowed bg-slate-50/60"
                      }`}
                    >
                      <input
                        type="checkbox"
                        disabled={!selectable}
                        checked={selected}
                        onChange={() => toggleAtm(atm.atm_id)}
                        className="h-4 w-4"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium text-slate-900">{atm.name}</div>
                        <div className="truncate text-xs text-slate-500">
                          {atm.atm_id} · {atm.branch}
                        </div>
                        {target?.last_error && (
                          <div className="mt-1 truncate text-xs text-rose-700" title={target.last_error}>
                            {target.last_error}
                          </div>
                        )}
                        {target && target.status !== "applied" && <TargetProgress target={target} compact />}
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-1 text-xs ${statusStyles[status] || statusStyles.pending}`}>
                        {statusLabels[status] || status}
                      </span>
                    </label>
                  );
                })}
              {!loadingDetails && atms.length === 0 && (
                <div className="px-3 py-4 text-center text-sm text-slate-500">لا توجد صرافات بعد</div>
              )}
            </div>
          </div>

          <div className="p-4">
            {error && (
              <div className="mb-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                <AlertCircle className="mt-0.5 shrink-0" size={17} />
                <span>{error}</span>
              </div>
            )}
            {message && (
              <div className="mb-3 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                <CheckCircle2 className="mt-0.5 shrink-0" size={17} />
                <span>{message}</span>
              </div>
            )}

            <div className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
              المحدد: {selectedAtms.length} · جديد: {selectedSummary.newTargets} · إعادة محاولة: {selectedSummary.retries}
            </div>

            <button
              onClick={assign}
              disabled={!selectedPackage || selectedAtms.length === 0 || assigning}
              className="focus-ring flex w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
              title="إرسال التعيين"
            >
              {selectedSummary.retries > 0 && selectedSummary.newTargets === 0 ? <RotateCcw size={17} /> : <Send size={17} />}
              <span>{assigning ? "جار الإرسال..." : `إرسال التعيين (${selectedAtms.length})`}</span>
            </button>
          </div>
          </aside>
        </>
      )}

      {activeTab === "monitor" && (
        <div className="space-y-5">
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-950">متابعة التنفيذ</h2>
                  <p className="mt-1 text-sm text-slate-500">{selectedPackageData?.version || "اختر حزمة من القائمة أعلاه"}</p>
                </div>
                <button
                  onClick={refreshDetails}
                  disabled={!selectedPackage || loadingDetails}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
                  title="تحديث التفاصيل"
                >
                  <RefreshCw size={16} />
                  <span>{loadingDetails ? "جار التحديث" : "تحديث"}</span>
                </button>
              </div>
            </div>

            {selectedPackageData && (
              <div className="grid gap-3 p-4 text-sm md:grid-cols-5">
                <div className="rounded-lg bg-slate-50 px-3 py-2">
                  <div className="text-slate-500">مستهدف</div>
                  <div className="mt-1 font-semibold text-slate-900">{detailCounts.total || selectedPackageData.total_targets}</div>
                </div>
                <div className="rounded-lg bg-emerald-50 px-3 py-2">
                  <div className="text-emerald-700">تم</div>
                  <div className="mt-1 font-semibold text-emerald-800">{detailCounts.applied || selectedPackageData.applied_targets}</div>
                </div>
                <div className="rounded-lg bg-amber-50 px-3 py-2">
                  <div className="text-amber-700">ينتظر</div>
                  <div className="mt-1 font-semibold text-amber-800">{detailCounts.pending}</div>
                </div>
                <div className="rounded-lg bg-sky-50 px-3 py-2">
                  <div className="text-sky-700">جاري</div>
                  <div className="mt-1 font-semibold text-sky-800">{detailCounts.downloading}</div>
                </div>
                <div className="rounded-lg bg-rose-50 px-3 py-2">
                  <div className="text-rose-700">فشل</div>
                  <div className="mt-1 font-semibold text-rose-800">{detailCounts.failed || selectedPackageData.failed_targets}</div>
                </div>
              </div>
            )}

            {error && (
              <div className="mx-4 mb-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                <AlertCircle className="mt-0.5 shrink-0" size={17} />
                <span>{error}</span>
              </div>
            )}
          </div>

          {details?.targets?.length > 0 ? (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-4 py-3 font-semibold text-slate-950">الصرافات المستهدفة</div>
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-4 py-3 text-right font-medium">الصراف</th>
                    <th className="px-4 py-3 text-right font-medium">الحالة</th>
                    <th className="px-4 py-3 text-right font-medium">التقدم</th>
                    <th className="px-4 py-3 text-right font-medium">المحاولات</th>
                    <th className="px-4 py-3 text-right font-medium">آخر فحص</th>
                    <th className="px-4 py-3 text-right font-medium">الخطأ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {details.targets.map((target) => (
                    <tr key={target.id}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">{target.atm.name}</div>
                        <div className="text-xs text-slate-500">{target.atm.atm_id}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full px-2 py-1 text-xs ${statusStyles[target.status] || statusStyles.pending}`}>
                          {statusLabels[target.status] || target.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <TargetProgress target={target} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1 text-slate-600">
                          <Clock3 size={14} />
                          {target.attempt_count}
                        </span>
                      </td>
                      <td className="px-4 py-3">{formatApiDate(target.last_checked_at)}</td>
                      <td className="max-w-xl px-4 py-3 text-rose-700">{target.last_error || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500 shadow-sm">
              لا توجد صرافات مستهدفة لهذه الحزمة بعد
            </div>
          )}
        </div>
      )}
    </section>
  );
}
