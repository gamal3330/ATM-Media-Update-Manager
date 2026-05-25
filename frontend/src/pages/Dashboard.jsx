import { RefreshCw } from "lucide-react";
import { formatLastSeenAge, isRecentlyOnline } from "../api/time";
import StatCard from "../components/StatCard";

export default function Dashboard({ atms, packages, cashSummary, loading, onRefresh }) {
  const online = atms.filter(isRecentlyOnline).length;
  const offline = atms.length - online;
  const pending = packages.reduce((total, item) => total + (item.pending_targets || 0), 0);
  const failed = packages.reduce((total, item) => total + (item.failed_targets || 0), 0);
  const pendingConfig = atms.filter((atm) => (atm.applied_config_version || 0) < (atm.config_version || 0)).length;

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">لوحة التحكم</h1>
          <p className="text-sm text-slate-500">متابعة حالة الصرافات وتحديثات الصور</p>
        </div>
        <button
          onClick={onRefresh}
          className="focus-ring flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50"
          title="تحديث البيانات"
        >
          <RefreshCw size={17} />
          <span>{loading ? "جار التحديث" : "تحديث"}</span>
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="عدد الصرافات" value={atms.length} tone="neutral" />
        <StatCard label="Online" value={online} tone="good" />
        <StatCard label="Offline" value={offline} tone="warn" />
        <StatCard label="Pending / Failed" value={`${pending} / ${failed}`} tone={failed ? "bad" : "neutral"} />
        <StatCard label="Pending Config" value={pendingConfig} tone={pendingConfig ? "warn" : "good"} />
        <StatCard label="Cash Low" value={cashSummary?.cash_low_atms || 0} tone={cashSummary?.cash_low_atms ? "warn" : "good"} />
        <StatCard label="Cash Empty" value={cashSummary?.cash_empty_atms || 0} tone={cashSummary?.cash_empty_atms ? "bad" : "good"} />
        <StatCard label="Cash Data Stale" value={cashSummary?.cash_stale_atms || 0} tone={cashSummary?.cash_stale_atms ? "warn" : "good"} />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">آخر الحزم</div>
          <div className="divide-y divide-slate-100">
            {packages.slice(0, 6).map((item) => (
              <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <div>
                  <div className="font-medium text-slate-900">{item.version}</div>
                  <div className="text-slate-500">{item.original_filename}</div>
                </div>
                <div className="text-slate-600">
                  {item.applied_targets} تم / {item.pending_targets} معلق / {item.failed_targets} فشل
                </div>
              </div>
            ))}
            {packages.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد حزم بعد</div>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">حالة الصرافات</div>
          <div className="divide-y divide-slate-100">
            {atms.slice(0, 8).map((atm) => (
              <div key={atm.atm_id} className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
                <div>
                  <div className="font-medium text-slate-900">{atm.name}</div>
                  <div className="text-slate-500">
                    {atm.atm_id} · {atm.branch} · {formatLastSeenAge(atm)}
                    {(atm.applied_config_version || 0) < (atm.config_version || 0) ? " · Pending Config Sync" : ""}
                  </div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs ${isRecentlyOnline(atm) ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                  {isRecentlyOnline(atm) ? "Online" : "Offline"}
                </span>
              </div>
            ))}
            {atms.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد صرافات بعد</div>}
          </div>
        </div>
      </div>
    </section>
  );
}
