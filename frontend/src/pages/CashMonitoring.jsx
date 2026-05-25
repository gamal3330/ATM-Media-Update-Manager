import { AlertTriangle, Banknote, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";
import StatCard from "../components/StatCard";

function statusTone(status) {
  const value = String(status || "").toUpperCase();
  if (value === "EMPTY" || value === "CRITICAL") return "bg-rose-50 text-rose-700";
  if (value === "LOW") return "bg-amber-50 text-amber-700";
  return "bg-emerald-50 text-emerald-700";
}

export default function CashMonitoring({ atms }) {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [selectedAtmId, setSelectedAtmId] = useState("");
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const cashEnabledAtms = useMemo(() => atms.filter((atm) => atm.cash_monitoring_enabled), [atms]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [summaryData, alertData] = await Promise.all([api.getCashSummary(), api.listCashAlerts()]);
      setSummary(summaryData);
      setAlerts(alertData);
      const nextAtmId = selectedAtmId || cashEnabledAtms[0]?.atm_id || atms[0]?.atm_id || "";
      if (nextAtmId) {
        setSelectedAtmId(nextAtmId);
        setDetails(await api.getCashAtm(nextAtmId));
      }
    } catch (err) {
      setError(err.message || "تعذر تحميل بيانات مراقبة النقد");
    } finally {
      setLoading(false);
    }
  }

  async function selectAtm(atmId) {
    setSelectedAtmId(atmId);
    setError("");
    try {
      setDetails(await api.getCashAtm(atmId));
    } catch (err) {
      setError(err.message || "تعذر تحميل بيانات الصراف");
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
            <Banknote size={25} />
            <span>مراقبة النقد</span>
          </h1>
          <p className="text-sm text-slate-500">قراءة Read-Only لحالة الكاسيتات والتنبيهات من ATM Unified Agent</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          title="تحديث بيانات النقد"
        >
          <RefreshCw size={17} />
          <span>{loading ? "جار التحديث" : "تحديث"}</span>
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Cash Low" value={summary?.cash_low_atms || 0} tone={summary?.cash_low_atms ? "warn" : "good"} />
        <StatCard label="Cash Empty" value={summary?.cash_empty_atms || 0} tone={summary?.cash_empty_atms ? "bad" : "good"} />
        <StatCard label="Data Stale" value={summary?.cash_stale_atms || 0} tone={summary?.cash_stale_atms ? "warn" : "good"} />
        <StatCard label="Open Alerts" value={summary?.open_alerts || 0} tone={summary?.open_alerts ? "bad" : "neutral"} />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-[320px_1fr]">
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">الصرافات</div>
          <div className="divide-y divide-slate-100">
            {atms.map((atm) => (
              <button
                key={atm.atm_id}
                onClick={() => selectAtm(atm.atm_id)}
                className={`block w-full px-4 py-3 text-right text-sm hover:bg-slate-50 ${
                  selectedAtmId === atm.atm_id ? "bg-teal-50" : ""
                }`}
              >
                <div className="font-medium text-slate-950">{atm.name}</div>
                <div className="mt-1 text-xs text-slate-500">
                  {atm.atm_id} · {atm.cash_monitoring_enabled ? "Cash Enabled" : "Cash Disabled"}
                </div>
              </button>
            ))}
            {atms.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد صرافات</div>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="font-medium text-slate-950">الكاسيتات</div>
            <div className="mt-1 text-xs text-slate-500">
              {details?.atm ? `${details.atm.atm_id} · آخر قراءة حسب كل كاسيت` : "اختر صرافاً"}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-4 py-3 text-right font-medium">Unit</th>
                  <th className="px-4 py-3 text-right font-medium">Cassette</th>
                  <th className="px-4 py-3 text-right font-medium">Currency</th>
                  <th className="px-4 py-3 text-right font-medium">Denom</th>
                  <th className="px-4 py-3 text-right font-medium">Current</th>
                  <th className="px-4 py-3 text-right font-medium">Threshold</th>
                  <th className="px-4 py-3 text-right font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Last Read</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(details?.units || []).map((unit) => (
                  <tr key={unit.id}>
                    <td className="px-4 py-3">{unit.unit_no}</td>
                    <td className="px-4 py-3">{unit.cassette_name || unit.cassette_id || "-"}</td>
                    <td className="px-4 py-3">{unit.currency}</td>
                    <td className="px-4 py-3">{unit.denomination}</td>
                    <td className="px-4 py-3 font-semibold text-slate-950">{unit.current_count}</td>
                    <td className="px-4 py-3">{unit.min_threshold}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-1 text-xs ${statusTone(unit.status)}`}>{unit.status}</span>
                    </td>
                    <td className="px-4 py-3">{formatApiDate(unit.read_at)}</td>
                  </tr>
                ))}
                {(!details || details.units.length === 0) && (
                  <tr>
                    <td colSpan="8" className="px-4 py-8 text-center text-slate-500">
                      لا توجد بيانات نقد بعد. فعّل Cash Monitoring وانتظر أول snapshot من الـ Agent.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-medium">
          <AlertTriangle size={18} />
          <span>التنبيهات المفتوحة</span>
        </div>
        <div className="divide-y divide-slate-100">
          {alerts.slice(0, 20).map((alert) => (
            <div key={alert.id} className="px-4 py-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-slate-950">{alert.message}</div>
                <span className={`rounded-full px-2 py-1 text-xs ${statusTone(alert.alert_type)}`}>{alert.alert_type}</span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Unit {alert.unit_no} · Current {alert.current_count} · Threshold {alert.threshold_count} · {formatApiDate(alert.opened_at)}
              </div>
            </div>
          ))}
          {alerts.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد تنبيهات مفتوحة</div>}
        </div>
      </div>
    </section>
  );
}
