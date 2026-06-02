import { AlertTriangle, Banknote, Download, FileText, PackageCheck, RefreshCw, Timer, TrendingDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate } from "../api/time";
import StatCard from "../components/StatCard";

function statusTone(status) {
  const value = String(status || "").toUpperCase();
  if (value.includes("EMPTY") || value.includes("CRITICAL") || value.includes("MISSING") || value.includes("INOP")) {
    return "bg-rose-50 text-rose-700";
  }
  if (value.includes("LOW") || value.includes("HIGH") || value.includes("RETRACT")) return "bg-amber-50 text-amber-700";
  if (value.includes("MISMATCH")) return "bg-rose-50 text-rose-700";
  return "bg-emerald-50 text-emerald-700";
}

function formatCashValue(value) {
  return new Intl.NumberFormat("en-US").format(value || 0);
}

function alertUnitLabel(alert) {
  if (alert.unit_no === 0) return "Reject/Retract";
  return `Cassette ${alert.unit_no}`;
}

function riskTone(risk) {
  const value = String(risk || "").toUpperCase();
  if (value === "CRITICAL") return "bg-rose-50 text-rose-700";
  if (value === "LOW") return "bg-amber-50 text-amber-700";
  if (value === "STALE") return "bg-slate-100 text-slate-600";
  if (value === "OK") return "bg-emerald-50 text-emerald-700";
  return "bg-slate-100 text-slate-600";
}

function formatDays(value) {
  if (value === null || value === undefined) return "-";
  if (Number(value) <= 0) return "الآن";
  if (Number(value) < 1) return "أقل من يوم";
  return `${Number(value).toFixed(1)} يوم`;
}

function downloadCsv(filename, rows) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function CashMonitoring({ atms }) {
  const [summary, setSummary] = useState(null);
  const [report, setReport] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [selectedAtmId, setSelectedAtmId] = useState("");
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const cashEnabledAtms = useMemo(() => atms.filter((atm) => atm.cash_monitoring_enabled), [atms]);
  const availableByCurrency = useMemo(() => {
    const totals = {};
    (details?.units || []).forEach((unit) => {
      const currency = unit.expected_currency || unit.reported_currency || "N/A";
      const denomination = Number(unit.expected_denomination || unit.reported_denomination || 0);
      totals[currency] = (totals[currency] || 0) + Number(unit.current_count || 0) * denomination;
    });
    return Object.entries(totals);
  }, [details]);
  const selectedAlerts = useMemo(() => {
    const selectedInternalId = details?.atm?.id;
    if (!selectedInternalId) return [];
    return alerts.filter((alert) => Number(alert.atm_id) === Number(selectedInternalId));
  }, [alerts, details]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [summaryData, alertData, reportData] = await Promise.all([api.getCashSummary(), api.listCashAlerts(), api.getCashReport()]);
      setSummary(summaryData);
      setAlerts(alertData);
      setReport(reportData);
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

  function exportReport() {
    const rows = [
      ["ATM ID", "Name", "Branch", "Last Read", "Stale", "Risk", "Total Notes", "Lowest Cassette", "Lowest Count", "Days To Empty", "Open Alerts"],
      ...(report?.atms || []).map((item) => [
        item.atm_id,
        item.name,
        item.branch,
        item.last_read_at || "-",
        item.is_stale ? "yes" : "no",
        item.highest_risk,
        item.total_note_count,
        item.lowest_cassette_no || "-",
        item.lowest_current_count ?? "-",
        item.forecast_days_to_empty ?? "-",
        item.open_alert_count,
      ]),
    ];
    downloadCsv("atm-cash-report.csv", rows);
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
          <p className="text-sm text-slate-500">CDM Read-Only لصرافات السحب فقط: dispense cassettes و reject/retract</p>
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Cash Low" value={summary?.cash_low_atms || 0} tone={summary?.cash_low_atms ? "warn" : "good"} />
        <StatCard label="Cash Critical" value={summary?.cash_critical_atms || 0} tone={summary?.cash_critical_atms ? "bad" : "good"} />
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
                  {atm.atm_id} · {atm.cash_monitoring_enabled ? "CDM Enabled" : "CDM Disabled"}
                </div>
              </button>
            ))}
            {atms.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد صرافات</div>}
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-600">
                <PackageCheck size={17} />
                <span>Available Cash</span>
              </div>
              <div className="mt-3 space-y-2">
                {availableByCurrency.map(([currency, value]) => (
                  <div key={currency} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                    <span className="font-medium text-slate-600">{currency}</span>
                    <span className="font-semibold text-slate-950">{formatCashValue(value)}</span>
                  </div>
                ))}
                {availableByCurrency.length === 0 && <div className="text-sm text-slate-500">لا توجد قراءة نقد بعد</div>}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-sm font-medium text-slate-600">Reject Bin</div>
              <div className="mt-3 flex items-end justify-between">
                <div className="text-3xl font-semibold text-slate-950">{details?.reject_retract?.reject_count ?? "-"}</div>
                <span className={`rounded-full px-2 py-1 text-xs ${statusTone(details?.reject_retract?.reject_status)}`}>
                  {details?.reject_retract?.reject_status || "-"}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Capacity {details?.reject_retract?.reject_max_capacity ?? "-"}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-sm font-medium text-slate-600">Retract Bin</div>
              <div className="mt-3 flex items-end justify-between">
                <div className="text-3xl font-semibold text-slate-950">{details?.reject_retract?.retract_count ?? "-"}</div>
                <span className={`rounded-full px-2 py-1 text-xs ${statusTone(details?.reject_retract?.retract_status)}`}>
                  {details?.reject_retract?.retract_status || "-"}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Capacity {details?.reject_retract?.retract_max_capacity ?? "-"}
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="font-medium text-slate-950">Dispense Cassettes</div>
            <div className="mt-1 text-xs text-slate-500">
              {details?.atm ? `${details.atm.atm_id} · ${details.atm.atm_cash_mode || "DISPENSE_ONLY"}` : "اختر صرافاً"}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-4 py-3 text-right font-medium">Cassette</th>
                  <th className="px-4 py-3 text-right font-medium">Expected</th>
                  <th className="px-4 py-3 text-right font-medium">Reported</th>
                  <th className="px-4 py-3 text-right font-medium">Current</th>
                  <th className="px-4 py-3 text-right font-medium">Low / Critical</th>
                  <th className="px-4 py-3 text-right font-medium">Reject</th>
                  <th className="px-4 py-3 text-right font-medium">Physical</th>
                  <th className="px-4 py-3 text-right font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Last Read</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(details?.units || []).map((unit) => (
                  <tr key={unit.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-950">{unit.cassette_no}</div>
                      <div className="text-xs text-slate-500">{unit.cassette_name || unit.cassette_id || "-"}</div>
                    </td>
                    <td className="px-4 py-3">
                      {unit.expected_currency} {unit.expected_denomination}
                    </td>
                    <td className="px-4 py-3">
                      <span className={unit.layout_match_status === "MATCH" ? "" : "font-semibold text-rose-700"}>
                        {unit.reported_currency} {unit.reported_denomination}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-950">{unit.current_count}</td>
                    <td className="px-4 py-3">{unit.low_threshold} / {unit.critical_threshold}</td>
                    <td className="px-4 py-3">{unit.reject_count}</td>
                    <td className="px-4 py-3">{unit.physical_status}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-1 text-xs ${statusTone(unit.status)}`}>{unit.status}</span>
                      {unit.layout_match_status !== "MATCH" && (
                        <div className="mt-1 text-xs font-medium text-rose-700">{unit.layout_match_status}</div>
                      )}
                    </td>
                    <td className="px-4 py-3">{formatApiDate(unit.read_at)}</td>
                  </tr>
                ))}
                {(!details || details.units.length === 0) && (
                  <tr>
                    <td colSpan="9" className="px-4 py-8 text-center text-slate-500">
                      لا توجد بيانات CDM بعد. فعّل Cash Monitoring وانتظر أول snapshot من الـ Agent.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
            <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                <div>
                  <div className="flex items-center gap-2 font-medium text-slate-950">
                    <TrendingDown size={18} />
                    <span>توقع نفاد النقد</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-500">مبني على آخر قراءات CDM الناجحة</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-3 text-right font-medium">Cassette</th>
                      <th className="px-4 py-3 text-right font-medium">الحالة</th>
                      <th className="px-4 py-3 text-right font-medium">معدل يومي</th>
                      <th className="px-4 py-3 text-right font-medium">إلى Low</th>
                      <th className="px-4 py-3 text-right font-medium">إلى Empty</th>
                      <th className="px-4 py-3 text-right font-medium">عينات</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(details?.forecasts || []).map((item) => (
                      <tr key={`${item.atm_id}-${item.cassette_no}`}>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-slate-950">{item.cassette_no}</div>
                          <div className="text-xs text-slate-500">{item.currency} {item.denomination}</div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${riskTone(item.risk)}`}>{item.risk}</span>
                        </td>
                        <td className="px-4 py-3">{item.notes_per_day ? `${formatCashValue(item.notes_per_day)} ورقة` : "-"}</td>
                        <td className="px-4 py-3">{formatDays(item.days_to_low)}</td>
                        <td className="px-4 py-3 font-semibold text-slate-950">{formatDays(item.days_to_empty)}</td>
                        <td className="px-4 py-3">{item.sample_count}</td>
                      </tr>
                    ))}
                    {(!details || (details.forecasts || []).length === 0) && (
                      <tr>
                        <td colSpan="6" className="px-4 py-8 text-center text-slate-500">
                          يحتاج التوقع إلى قراءتين نقديتين ناجحتين على الأقل.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
                <div className="flex items-center gap-2 font-medium text-slate-950">
                  <FileText size={18} />
                  <span>تقرير مختصر</span>
                </div>
                <button
                  onClick={exportReport}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs hover:bg-slate-50"
                  disabled={!report?.atms?.length}
                >
                  <Download size={15} />
                  CSV
                </button>
              </div>
              <div className="space-y-3 p-4">
                <div className="rounded-lg bg-slate-50 px-3 py-3">
                  <div className="text-xs font-medium text-slate-500">صرافات مفعلة</div>
                  <div className="mt-1 text-2xl font-semibold text-slate-950">{report?.atms?.length || 0}</div>
                </div>
                <div className="rounded-lg bg-slate-50 px-3 py-3">
                  <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                    <Timer size={15} />
                    <span>أقرب نفاد متوقع</span>
                  </div>
                  <div className="mt-1 text-2xl font-semibold text-slate-950">
                    {formatDays(report?.forecast_risks?.[0]?.days_to_empty)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {report?.forecast_risks?.[0]
                      ? `${report.forecast_risks[0].atm_name} · Cassette ${report.forecast_risks[0].cassette_no}`
                      : "لا توجد مخاطر حالية"}
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold text-slate-500">أعلى المخاطر</div>
                  <div className="space-y-2">
                    {(report?.forecast_risks || []).slice(0, 4).map((item) => (
                      <div key={`${item.atm_id}-${item.cassette_no}`} className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-2 text-xs">
                        <div>
                          <div className="font-semibold text-slate-950">{item.atm_name}</div>
                          <div className="text-slate-500">Cassette {item.cassette_no} · {item.current_count} ورقة</div>
                        </div>
                        <span className={`rounded-full px-2 py-1 font-semibold ${riskTone(item.risk)}`}>{formatDays(item.days_to_empty)}</span>
                      </div>
                    ))}
                    {(!report?.forecast_risks || report.forecast_risks.length === 0) && (
                      <div className="rounded-lg bg-slate-50 px-3 py-3 text-center text-xs text-slate-500">لا توجد مخاطر نقد حالية</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
      </div>
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 font-medium">
          <AlertTriangle size={18} />
          <span>التنبيهات المفتوحة</span>
        </div>
        <div className="divide-y divide-slate-100">
          {selectedAlerts.slice(0, 20).map((alert) => (
            <div key={alert.id} className="px-4 py-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-slate-950">{alert.message}</div>
                <span className={`rounded-full px-2 py-1 text-xs ${statusTone(alert.alert_type)}`}>{alert.alert_type}</span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {alertUnitLabel(alert)} · Current {alert.current_count} · Threshold {alert.threshold_count} · {formatApiDate(alert.opened_at)}
              </div>
            </div>
          ))}
          {selectedAlerts.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد تنبيهات مفتوحة لهذا الصراف</div>}
        </div>
      </div>
    </section>
  );
}
