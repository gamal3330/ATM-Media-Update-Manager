import {
  AlertTriangle,
  Banknote,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  Download,
  Landmark,
  RefreshCw,
  Search,
  TerminalSquare,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate, formatLocalWallDate } from "../api/time";

const WITHDRAWAL_LIMIT = 300;

function normalizeText(value) {
  return String(value || "").toLowerCase().trim();
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US") : "-";
}

function formatMoney(value, currency = "YER") {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number === 0) return "-";
  return `${currency} ${number.toLocaleString("en-US")}`;
}

function atmSearchText(atm) {
  return [atm?.atm_id, atm?.name, atm?.branch, atm?.vpn_ip, atm?.agent_version, atm?.xfs_profile].join(" ");
}

function eventSearchText(event) {
  return [
    event?.atm?.atm_id,
    event?.atm?.name,
    event?.atm?.branch,
    event?.transaction_serial,
    event?.rrn,
    event?.stan,
    event?.auth_code,
    event?.card_masked,
    event?.amount,
    event?.currency,
  ].join(" ");
}

function riskMeta(risk) {
  const value = normalizeText(risk).toUpperCase();
  if (value === "CRITICAL") return { label: "حرج", tone: "bg-rose-50 text-rose-700" };
  if (value === "LOW") return { label: "منخفض", tone: "bg-amber-50 text-amber-700" };
  if (value === "STALE") return { label: "قديم", tone: "bg-sky-50 text-sky-700" };
  if (value === "OK") return { label: "جيد", tone: "bg-emerald-50 text-emerald-700" };
  return { label: "غير معروف", tone: "bg-slate-100 text-slate-600" };
}

function completedLabel(event) {
  const details = event?.details_json || {};
  if (details.completed === true) return "مكتملة";
  if (details.dispense_success && !details.money_taken) return "النقد لم يؤخذ";
  return "غير مكتملة";
}

function isWithdrawalCompleted(event) {
  return event?.details_json?.completed === true;
}

function cassetteText(items) {
  if (!Array.isArray(items) || items.length === 0) return "-";
  return items.map((item) => `CAS ${item.cassette_no}: ${item.out}`).join(" | ");
}

function StatCard({ label, value, icon: Icon, tone = "slate", note }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-950",
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    rose: "border-rose-200 bg-rose-50 text-rose-950",
    sky: "border-sky-200 bg-sky-50 text-sky-950",
    teal: "border-teal-200 bg-teal-50 text-teal-950",
  };

  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <Icon size={18} className="opacity-70" />
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none">{value}</div>
      {note && <div className="mt-1 text-xs text-slate-500">{note}</div>}
    </div>
  );
}

function SectionHeader({ icon: Icon, title, meta, action }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <Icon size={19} className="text-slate-500" />
        <h2 className="text-lg font-semibold text-slate-950">{title}</h2>
        {meta && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{meta}</span>}
      </div>
      {action}
    </div>
  );
}

function EmptyPanel({ children }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-10 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}

function TableShell({ children }) {
  return <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">{children}</div>;
}

function downloadCsv(filename, rows) {
  if (!rows.length) return;
  const csv = rows
    .map((row) =>
      row
        .map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`)
        .join(","),
    )
    .join("\n");
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function Reports({ atms = [], cashSummary }) {
  const [branchFilter, setBranchFilter] = useState("all");
  const [atmFilter, setAtmFilter] = useState("");
  const [query, setQuery] = useState("");
  const [fromAt, setFromAt] = useState("");
  const [toAt, setToAt] = useState("");
  const [cashReport, setCashReport] = useState(null);
  const [cashLoading, setCashLoading] = useState(false);
  const [cashError, setCashError] = useState("");
  const [withdrawals, setWithdrawals] = useState([]);
  const [withdrawalsLoaded, setWithdrawalsLoaded] = useState(false);
  const [withdrawalsLoading, setWithdrawalsLoading] = useState(false);
  const [withdrawalsError, setWithdrawalsError] = useState("");

  const branches = useMemo(() => {
    return [...new Set(atms.map((atm) => atm.branch).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
  }, [atms]);

  const filteredAtms = useMemo(() => {
    const needle = normalizeText(query);
    return atms.filter((atm) => {
      if (branchFilter !== "all" && atm.branch !== branchFilter) return false;
      if (atmFilter && atm.atm_id !== atmFilter) return false;
      if (needle && !normalizeText(atmSearchText(atm)).includes(needle)) return false;
      return true;
    });
  }, [atms, atmFilter, branchFilter, query]);

  const cashRows = useMemo(() => {
    const byAtmId = new Set(filteredAtms.map((atm) => atm.atm_id));
    return (cashReport?.atms || []).filter((row) => byAtmId.has(row.atm_id));
  }, [cashReport, filteredAtms]);

  const filteredWithdrawals = useMemo(() => {
    const atmIds = new Set(filteredAtms.map((atm) => atm.atm_id));
    const needle = normalizeText(query);
    return withdrawals.filter((event) => {
      const eventAtmId = event?.atm?.atm_id || "";
      if (eventAtmId && !atmIds.has(eventAtmId)) return false;
      if (branchFilter !== "all" && event?.atm?.branch !== branchFilter) return false;
      if (atmFilter && eventAtmId !== atmFilter) return false;
      if (needle && !normalizeText(eventSearchText(event)).includes(needle)) return false;
      return true;
    });
  }, [atmFilter, branchFilter, filteredAtms, query, withdrawals]);

  const cashStats = useMemo(() => {
    const totals = {};
    cashRows.forEach((row) => {
      Object.entries(row.totals_by_currency || {}).forEach(([currency, amount]) => {
        totals[currency] = (totals[currency] || 0) + (Number(amount) || 0);
      });
    });
    return {
      totalAtms: cashRows.length,
      stale: cashRows.filter((row) => row.is_stale).length,
      alerts: cashRows.reduce((sum, row) => sum + (Number(row.open_alert_count) || 0), 0),
      low: cashRows.filter((row) => row.highest_risk === "LOW").length,
      critical: cashRows.filter((row) => row.highest_risk === "CRITICAL").length,
      totals,
    };
  }, [cashRows]);

  const withdrawalStats = useMemo(() => {
    const completed = filteredWithdrawals.filter(isWithdrawalCompleted);
    const amountByCurrency = {};
    completed.forEach((event) => {
      const currency = event.currency || "YER";
      amountByCurrency[currency] = (amountByCurrency[currency] || 0) + (Number(event.amount) || 0);
    });
    return {
      total: filteredWithdrawals.length,
      completed: completed.length,
      incomplete: filteredWithdrawals.length - completed.length,
      timeoutWarnings: filteredWithdrawals.filter((event) => event.details_json?.take_cash_timeout).length,
      amountByCurrency,
    };
  }, [filteredWithdrawals]);

  const canLoadWithdrawals = Boolean(fromAt && toAt && new Date(fromAt).getTime() <= new Date(toAt).getTime());

  async function loadCashReport() {
    setCashLoading(true);
    setCashError("");
    try {
      setCashReport(await api.getCashReport());
    } catch (err) {
      setCashError(err.message || "تعذر تحميل تقرير النقد");
    } finally {
      setCashLoading(false);
    }
  }

  async function loadWithdrawals() {
    if (!canLoadWithdrawals) return;
    setWithdrawalsLoading(true);
    setWithdrawalsError("");
    try {
      const data = await api.listJournalLogs({
        atmId: atmFilter,
        eventType: "TRANSACTION_END",
        transactionType: "WID",
        fromAt,
        toAt,
        page: 1,
        pageSize: WITHDRAWAL_LIMIT,
        limit: WITHDRAWAL_LIMIT,
      });
      setWithdrawals(Array.isArray(data) ? data : []);
      setWithdrawalsLoaded(true);
    } catch (err) {
      setWithdrawalsError(err.message || "تعذر تحميل عمليات السحب");
    } finally {
      setWithdrawalsLoading(false);
    }
  }

  function exportWithdrawals() {
    downloadCsv("withdrawal-report.csv", [
      ["ATM", "Branch", "Occurred At", "Amount", "Currency", "RRN", "STAN", "Auth Code", "Card", "Status", "Cassettes"],
      ...filteredWithdrawals.map((event) => [
        event.atm?.atm_id || "",
        event.atm?.branch || "",
        formatLocalWallDate(event.occurred_at),
        event.amount || "",
        event.currency || "",
        event.rrn || "",
        event.stan || "",
        event.auth_code || "",
        event.card_masked || "",
        completedLabel(event),
        cassetteText(event.cassette_outputs_json),
      ]),
    ]);
  }

  const cashTotalText = Object.entries(cashStats.totals)
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(" / ");
  const withdrawalTotalText = Object.entries(withdrawalStats.amountByCurrency)
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(" / ");

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">التقارير</h1>
          <div className="mt-1 text-sm text-slate-500">تقارير النقد وعمليات السحب من Journal.</div>
        </div>
        <button
          type="button"
          onClick={loadCashReport}
          disabled={cashLoading}
          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-teal-200 bg-teal-50 px-3 text-sm font-semibold text-teal-800 hover:bg-teal-100 disabled:opacity-60"
        >
          <RefreshCw size={16} className={cashLoading ? "animate-spin" : ""} />
          <span>{cashLoading ? "جاري تحديث النقد" : "تحديث تقرير النقد"}</span>
        </button>
      </div>

      <div className="mb-5 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-[minmax(180px,0.9fr)_minmax(200px,1fr)_minmax(240px,1.3fr)_minmax(180px,1fr)_minmax(180px,1fr)_minmax(120px,auto)]">
          <select
            value={branchFilter}
            onChange={(event) => setBranchFilter(event.target.value)}
            className="focus-ring h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="all">كل الفروع</option>
            {branches.map((branch) => (
              <option key={branch} value={branch}>
                {branch}
              </option>
            ))}
          </select>

          <label className="relative block">
            <TerminalSquare className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <select
              value={atmFilter}
              onChange={(event) => setAtmFilter(event.target.value)}
              className="focus-ring h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
            >
              <option value="">كل الصرافات</option>
              {atms.map((atm) => (
                <option key={atm.atm_id} value={atm.atm_id}>
                  {atm.name} - ATM {atm.atm_id}
                </option>
              ))}
            </select>
          </label>

          <label className="relative block">
            <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="focus-ring h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              placeholder="بحث بالصراف، الفرع، IP، RRN أو البطاقة"
            />
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={fromAt}
              onChange={(event) => {
                setFromAt(event.target.value);
                setWithdrawalsLoaded(false);
                setWithdrawals([]);
              }}
              className="focus-ring h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="من"
            />
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={toAt}
              onChange={(event) => {
                setToAt(event.target.value);
                setWithdrawalsLoaded(false);
                setWithdrawals([]);
              }}
              className="focus-ring h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="إلى"
            />
          </label>

          <button
            type="button"
            onClick={loadWithdrawals}
            disabled={!canLoadWithdrawals || withdrawalsLoading}
            className="focus-ring inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Search size={16} className={withdrawalsLoading ? "animate-pulse" : ""} />
            <span>{withdrawalsLoading ? "جاري العرض" : "عرض السحب"}</span>
          </button>
        </div>
        {fromAt && toAt && !canLoadWithdrawals && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            وقت البداية يجب أن يكون قبل وقت النهاية.
          </div>
        )}
      </div>

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label="تنبيهات نقد" value={cashSummary?.open_alerts ?? "-"} icon={Banknote} tone={cashSummary?.open_alerts ? "amber" : "emerald"} />
        <StatCard label="عمليات السحب" value={withdrawalStats.total} icon={CreditCard} note={withdrawalTotalText || "حسب الفترة المحددة"} />
        <StatCard label="الصرافات المطابقة" value={filteredAtms.length} icon={Landmark} />
      </div>

      <div className="mb-6">
        <SectionHeader
          icon={Banknote}
          title="تقرير النقد"
          meta={cashReport ? `آخر تحديث ${formatApiDate(cashReport.generated_at)}` : "اضغط تحديث تقرير النقد"}
          action={
            <button
              type="button"
              onClick={loadCashReport}
              disabled={cashLoading}
              className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50 disabled:opacity-60"
            >
              <RefreshCw size={16} className={cashLoading ? "animate-spin" : ""} />
              <span>تحديث</span>
            </button>
          }
        />
        {cashError && <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{cashError}</div>}
        <div className="mb-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard label="صرافات النقد" value={cashReport ? cashStats.totalAtms : cashSummary?.atm_count ?? "-"} icon={Landmark} />
          <StatCard label="منخفض" value={cashSummary?.cash_low_units ?? cashStats.low} icon={AlertTriangle} tone={cashSummary?.cash_low_units ? "amber" : "emerald"} />
          <StatCard label="حرج / فارغ" value={(cashSummary?.cash_critical_units || 0) + (cashSummary?.cash_empty_units || 0)} icon={AlertTriangle} tone={(cashSummary?.cash_critical_units || cashSummary?.cash_empty_units) ? "rose" : "emerald"} />
          <StatCard label="قراءات قديمة" value={cashReport ? cashStats.stale : cashSummary?.cash_stale_atms ?? "-"} icon={RefreshCw} tone={cashStats.stale ? "amber" : "emerald"} />
          <StatCard label="إجمالي النقد" value={cashTotalText || "-"} icon={Banknote} tone="sky" />
        </div>
        {!cashReport ? (
          <EmptyPanel>اضغط تحديث تقرير النقد لعرض التفاصيل حسب الصراف والكاسيتات.</EmptyPanel>
        ) : (
          <TableShell>
            <div className="max-h-[420px] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="sticky top-0 bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-right font-semibold">الصراف</th>
                    <th className="px-3 py-2 text-right font-semibold">المخاطر</th>
                    <th className="px-3 py-2 text-right font-semibold">إجمالي النقد</th>
                    <th className="px-3 py-2 text-right font-semibold">الأوراق</th>
                    <th className="px-3 py-2 text-right font-semibold">أقل كاسيت</th>
                    <th className="px-3 py-2 text-right font-semibold">آخر قراءة</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {cashRows.map((row) => {
                    const risk = riskMeta(row.highest_risk);
                    return (
                      <tr key={row.atm_id} className="hover:bg-slate-50">
                        <td className="px-3 py-2">
                          <div className="font-semibold text-slate-950">{row.name}</div>
                          <div className="text-xs text-slate-500">ATM {row.atm_id} · {row.branch || "-"}</div>
                        </td>
                        <td className="px-3 py-2">
                          <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${risk.tone}`}>{risk.label}</span>
                          {row.open_alert_count > 0 && <div className="mt-1 text-xs text-amber-700">{row.open_alert_count} تنبيه مفتوح</div>}
                        </td>
                        <td className="px-3 py-2 font-semibold text-slate-900">
                          {Object.entries(row.totals_by_currency || {}).map(([currency, amount]) => formatMoney(amount, currency)).join(" / ") || "-"}
                        </td>
                        <td className="px-3 py-2">{formatNumber(row.total_note_count)}</td>
                        <td className="px-3 py-2">
                          {row.lowest_cassette_no ? `CAS ${row.lowest_cassette_no} · ${formatNumber(row.lowest_current_count)} ورقة` : "-"}
                        </td>
                        <td className="px-3 py-2">
                          <div>{formatApiDate(row.last_read_at)}</div>
                          {row.is_stale && <div className="text-xs text-amber-700">قراءة قديمة</div>}
                        </td>
                      </tr>
                    );
                  })}
                  {cashRows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-sm text-slate-500">لا توجد نتائج نقد مطابقة.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </TableShell>
        )}
      </div>

      <div>
        <SectionHeader
          icon={CreditCard}
          title="تقرير عمليات السحب"
          meta={withdrawalsLoaded ? `${filteredWithdrawals.length} عملية` : "حدد الفترة ثم اضغط عرض السحب"}
          action={
            withdrawalsLoaded && filteredWithdrawals.length > 0 ? (
              <button
                type="button"
                onClick={exportWithdrawals}
                className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
              >
                <Download size={16} />
                <span>CSV</span>
              </button>
            ) : null
          }
        />
        {withdrawalsError && <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{withdrawalsError}</div>}
        <div className="mb-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="العمليات" value={withdrawalStats.total} icon={ClipboardList} />
          <StatCard label="مكتملة" value={withdrawalStats.completed} icon={CheckCircle2} tone="emerald" />
          <StatCard label="غير مكتملة" value={withdrawalStats.incomplete} icon={AlertTriangle} tone={withdrawalStats.incomplete ? "amber" : "emerald"} />
          <StatCard label="إجمالي السحب" value={withdrawalTotalText || "-"} icon={BarChart3} tone="sky" />
        </div>
        {!withdrawalsLoaded ? (
          <EmptyPanel>لن يتم تحميل عمليات السحب قبل تحديد الفترة والضغط على عرض السحب.</EmptyPanel>
        ) : (
          <TableShell>
            <div className="max-h-[520px] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="sticky top-0 bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2 text-right font-semibold">الصراف</th>
                    <th className="px-3 py-2 text-right font-semibold">الوقت</th>
                    <th className="px-3 py-2 text-right font-semibold">المبلغ</th>
                    <th className="px-3 py-2 text-right font-semibold">RRN / STAN</th>
                    <th className="px-3 py-2 text-right font-semibold">البطاقة</th>
                    <th className="px-3 py-2 text-right font-semibold">الحالة</th>
                    <th className="px-3 py-2 text-right font-semibold">الكاسيت</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredWithdrawals.map((event) => (
                    <tr key={event.id} className="hover:bg-slate-50">
                      <td className="px-3 py-2">
                        <div className="font-semibold text-slate-950">{event.atm?.name || "-"}</div>
                        <div className="text-xs text-slate-500">ATM {event.atm?.atm_id || "-"} · {event.atm?.branch || "-"}</div>
                      </td>
                      <td className="px-3 py-2">{formatLocalWallDate(event.occurred_at)}</td>
                      <td className="px-3 py-2 font-semibold">{formatMoney(event.amount, event.currency)}</td>
                      <td className="px-3 py-2 font-mono text-xs">
                        <div>{event.rrn || "-"}</div>
                        <div>{event.stan || "-"}</div>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{event.card_masked || "-"}</td>
                      <td className="px-3 py-2">
                        <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${isWithdrawalCompleted(event) ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                          {completedLabel(event)}
                        </span>
                        {event.details_json?.take_cash_timeout && <div className="mt-1 text-xs text-amber-700">Timeout</div>}
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-600">{cassetteText(event.cassette_outputs_json)}</td>
                    </tr>
                  ))}
                  {filteredWithdrawals.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-8 text-center text-sm text-slate-500">لا توجد عمليات سحب مطابقة.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {withdrawals.length >= WITHDRAWAL_LIMIT && (
              <div className="border-t border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                تم عرض أول {WITHDRAWAL_LIMIT} عملية فقط. ضيّق الفترة أو اختر صرافاً محدداً لنتيجة أدق.
              </div>
            )}
          </TableShell>
        )}
      </div>
    </section>
  );
}
