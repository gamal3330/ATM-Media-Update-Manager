import { AlertCircle, CheckCircle2, FileArchive, Send, UploadCloud, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { api } from "../api/client";

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function validateUpload({ file, version }) {
  if (!file) return "اختر ملف ZIP أولاً.";
  if (!file.name.toLowerCase().endsWith(".zip")) return "يجب اختيار ملف بصيغة ZIP.";
  if (version.trim().length > 120) return "رقم الإصدار يجب ألا يتجاوز 120 حرفاً.";
  return "";
}

export default function UploadPackage({ onUploaded, onOpenPackages }) {
  const [file, setFile] = useState(null);
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [uploadedPackage, setUploadedPackage] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef(null);

  const expectedVersion = useMemo(() => {
    if (version.trim()) return version.trim();
    return "سيتم إنشاؤه تلقائياً";
  }, [version]);

  function clearFile() {
    setFile(null);
    setError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setUploadedPackage(null);

    const validationError = validateUpload({ file, version });
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (version.trim()) formData.append("version", version.trim());
      if (notes.trim()) formData.append("notes", notes.trim());

      const result = await api.uploadPackage(formData);
      setUploadedPackage(result);
      setVersion("");
      setNotes("");
      clearFile();
      onUploaded();
    } catch (err) {
      setError(err.message || "فشل رفع الحزمة");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-slate-950">رفع حزمة صور</h1>
        <p className="text-sm text-slate-500">رفع الحزمة ثم تعيينها للصرافات من صفحة التحديثات</p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <form noValidate onSubmit={submit} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-5 grid gap-3 md:grid-cols-3">
            {[
              ["1", "اختيار ZIP"],
              ["2", "حفظ كإصدار"],
              ["3", "تعيين لاحق"],
            ].map(([number, label]) => (
              <div key={number} className="rounded-lg bg-slate-50 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-white">
                    {number}
                  </span>
                  <span className="text-sm font-medium text-slate-900">{label}</span>
                </div>
              </div>
            ))}
          </div>

          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">ملف ZIP</span>
            <div className={`rounded-lg border px-4 py-4 ${error && !file ? "border-rose-300 bg-rose-50" : "border-slate-300 bg-white"}`}>
              <input
                ref={fileInputRef}
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                type="file"
                accept=".zip"
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setError("");
                  setUploadedPackage(null);
                }}
              />

              {file && (
                <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileArchive className="shrink-0 text-teal-700" size={18} />
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-900">{file.name}</div>
                      <div className="text-xs text-slate-500">{formatBytes(file.size)}</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={clearFile}
                    className="focus-ring rounded-lg p-1 text-slate-500 hover:bg-white hover:text-slate-900"
                    title="إزالة الملف"
                  >
                    <X size={17} />
                  </button>
                </div>
              )}
            </div>
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">رقم الإصدار</span>
              <input
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                value={version}
                onChange={(event) => setVersion(event.target.value)}
                placeholder="اختياري"
                maxLength={120}
              />
            </label>

            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
              <div className="text-slate-500">الإصدار الناتج</div>
              <div className="mt-1 truncate font-medium text-slate-900">{expectedVersion}</div>
            </div>
          </div>

          <label className="mt-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">ملاحظات</span>
            <textarea
              className="focus-ring min-h-28 w-full rounded-lg border border-slate-300 px-3 py-2"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="اختياري"
            />
          </label>

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              <AlertCircle className="mt-0.5 shrink-0" size={17} />
              <span>{error}</span>
            </div>
          )}

          {uploadedPackage && (
            <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 shrink-0" size={17} />
                <div>
                  <div className="font-medium">تم رفع الحزمة بنجاح.</div>
                  <div className="mt-1">الإصدار: {uploadedPackage.version}</div>
                </div>
              </div>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            <button
              disabled={loading}
              className="focus-ring flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
              title="رفع الحزمة"
            >
              <UploadCloud size={18} />
              <span>{loading ? "جار الرفع..." : "رفع الحزمة"}</span>
            </button>

            {uploadedPackage && (
              <button
                type="button"
                onClick={onOpenPackages}
                className="focus-ring flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
                title="الانتقال للتعيين"
              >
                <Send size={18} />
                <span>الانتقال للتعيين</span>
              </button>
            )}
          </div>
        </form>

        <aside className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-950">ملخص الرفع</h2>

          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-slate-500">الملف</dt>
              <dd className="mt-1 font-medium text-slate-900">{file?.name || uploadedPackage?.original_filename || "-"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">الحجم</dt>
              <dd className="mt-1 font-medium text-slate-900">
                {file ? formatBytes(file.size) : uploadedPackage ? formatBytes(uploadedPackage.size_bytes) : "-"}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">الحالة بعد الرفع</dt>
              <dd className="mt-1">
                <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700">غير معيّنة</span>
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">طريقة التطبيق على الصراف</dt>
              <dd className="mt-1 text-slate-700">استبدال محتوى المسار المحدد بالكامل بمحتوى ZIP الآمن، بما في ذلك المجلدات</dd>
            </div>
            <div>
              <dt className="text-slate-500">الامتدادات داخل ZIP</dt>
              <dd className="mt-1 text-slate-700">jpg, jpeg, png, bmp, gif, pcx</dd>
            </div>
          </dl>

          {uploadedPackage?.sha256 && (
            <div className="mt-5 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
              <div className="mb-1 font-medium text-slate-700">SHA256</div>
              <div className="break-all font-mono" dir="ltr">{uploadedPackage.sha256}</div>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
