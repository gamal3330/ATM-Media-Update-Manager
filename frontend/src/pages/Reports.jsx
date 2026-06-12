import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  Download,
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

function StatCard({ label, value, icon: Icon, tone = "slate", note, valueClassName = "mt-2 text-2xl font-semibold leading-none" }) {
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
      <div className={valueClassName}>{value}</div>
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function exportRowCells(row) {
  return Array.isArray(row) ? row : row.cells || [];
}

function exportRowClass(row) {
  return Array.isArray(row) ? "" : row.className || "";
}

function exportTableHtml(title, rows) {
  const [headers = [], ...bodyRows] = rows;
  return `
    <section>
      <h2>${escapeHtml(title)}</h2>
      <table>
        <thead>
          <tr>${headers.map((cell) => `<th>${escapeHtml(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${bodyRows
            .map((row) => {
              const rowClass = exportRowClass(row);
              const classAttribute = rowClass ? ` class="${escapeHtml(rowClass)}"` : "";
              return `<tr${classAttribute}>${exportRowCells(row).map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </section>
  `;
}

function downloadExcel(filename, title, rows) {
  if (!rows.length) return;
  const html = `<!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body { direction: rtl; font-family: Arial, Tahoma, sans-serif; }
          table { border-collapse: collapse; width: 100%; }
          th, td { border: 1px solid #cbd5e1; padding: 8px; text-align: right; }
          th { background: #e0f2fe; color: #0f172a; font-weight: 700; }
          .row-completed td { background: #ecfdf5; color: #064e3b; }
          .row-incomplete td { background: #fff1f2; color: #9f1239; font-weight: 700; }
        </style>
      </head>
      <body>${exportTableHtml(title, rows)}</body>
    </html>`;
  const blob = new Blob([`\uFEFF${html}`], { type: "application/vnd.ms-excel;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function printPdf(title, sections, metaLines = []) {
  const printable = window.open("", "_blank");
  if (!printable) return;
  const metaHtml = metaLines.length
    ? `<div class="meta">${metaLines.map((line) => `<div>${escapeHtml(line)}</div>`).join("")}</div>`
    : "";
  const html = `<!doctype html>
    <html lang="ar" dir="rtl">
      <head>
        <meta charset="utf-8" />
        <title>${escapeHtml(title)}</title>
        <style>
          @page { size: A4 landscape; margin: 12mm; }
          body { direction: rtl; color: #0f172a; font-family: Arial, Tahoma, sans-serif; }
          h1 { margin: 0 0 10px; font-size: 22px; text-align: center; }
          h2 { margin: 18px 0 8px; font-size: 17px; }
          .meta { margin-bottom: 14px; color: #64748b; font-size: 12px; line-height: 1.7; text-align: center; }
          table { border-collapse: collapse; width: 100%; page-break-inside: auto; }
          tr { page-break-inside: avoid; page-break-after: auto; }
          th, td { border: 1px solid #cbd5e1; padding: 6px; text-align: right; font-size: 11px; vertical-align: top; }
          th { background: #e0f2fe; color: #0f172a; font-weight: 700; }
          .row-completed td { background: #ecfdf5; color: #064e3b; }
          .row-incomplete td { background: #fff1f2; color: #9f1239; font-weight: 700; }
        </style>
      </head>
      <body>
        <h1>${escapeHtml(title)}</h1>
        ${metaHtml}
        ${sections.map((section) => exportTableHtml(section.title, section.rows)).join("")}
        <script>window.addEventListener("load", () => setTimeout(() => window.print(), 250));</script>
      </body>
    </html>`;
  printable.document.open();
  printable.document.write(html);
  printable.document.close();
}

export default function Reports({ atms = [] }) {
  const [reportMode, setReportMode] = useState("summary");
  const [branchFilter, setBranchFilter] = useState("all");
  const [atmFilter, setAtmFilter] = useState("");
  const [query, setQuery] = useState("");
  const [fromAt, setFromAt] = useState("");
  const [toAt, setToAt] = useState("");
  const [withdrawalSummary, setWithdrawalSummary] = useState(null);
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

  const withdrawalStats = useMemo(() => {
    if (withdrawalSummary) {
      return {
        total: withdrawalSummary.total || 0,
        completed: withdrawalSummary.completed || 0,
        incomplete: withdrawalSummary.incomplete || 0,
        timeoutWarnings: 0,
        amountByCurrency: withdrawalSummary.amount_by_currency || {},
      };
    }

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
  }, [filteredWithdrawals, withdrawalSummary]);

  const canLoadWithdrawals = Boolean(fromAt && toAt && new Date(fromAt).getTime() <= new Date(toAt).getTime());

  function resetReportData() {
    setWithdrawalSummary(null);
    setWithdrawals([]);
    setWithdrawalsLoaded(false);
    setWithdrawalsError("");
  }

  async function loadWithdrawals() {
    if (!canLoadWithdrawals) return;
    setWithdrawalsLoading(true);
    setWithdrawalsError("");
    try {
      const params = {
        atmId: atmFilter,
        branch: branchFilter !== "all" ? branchFilter : "",
        search: query.trim(),
        eventType: "TRANSACTION_END",
        transactionType: "WID",
        fromAt,
        toAt,
      };
      const summaryRequest = api.getJournalWithdrawalSummary(params);
      if (reportMode === "summary") {
        const summary = await summaryRequest;
        setWithdrawalSummary(summary);
        setWithdrawals([]);
      } else {
        const [summary, data] = await Promise.all([
          summaryRequest,
          api.listJournalLogs({
            ...params,
            page: 1,
            pageSize: WITHDRAWAL_LIMIT,
            limit: WITHDRAWAL_LIMIT,
          }),
        ]);
        setWithdrawalSummary(summary);
        setWithdrawals(Array.isArray(data) ? data : []);
      }
      setWithdrawalsLoaded(true);
    } catch (err) {
      setWithdrawalsError(err.message || "تعذر تحميل عمليات السحب");
    } finally {
      setWithdrawalsLoading(false);
    }
  }

  function withdrawalExportRows() {
    return [
      ["ATM", "Branch", "Occurred At", "Amount", "Currency", "RRN", "STAN", "Auth Code", "Card", "Status", "Cassettes"],
      ...filteredWithdrawals.map((event) => ({
        className: isWithdrawalCompleted(event) ? "row-completed" : "row-incomplete",
        cells: [
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
        ],
      })),
    ];
  }

  function withdrawalSummaryExportRows() {
    return [
      ["البند", "القيمة"],
      { cells: ["إجمالي العمليات", withdrawalStats.total] },
      { className: "row-completed", cells: ["العمليات الناجحة", withdrawalStats.completed] },
      { className: "row-incomplete", cells: ["العمليات غير الناجحة", withdrawalStats.incomplete] },
      { cells: ["إجمالي السحب", withdrawalTotalText || "-"] },
    ];
  }

  function currentExportRows() {
    return reportMode === "summary" ? withdrawalSummaryExportRows() : withdrawalExportRows();
  }

  function currentReportTitle() {
    return reportMode === "summary" ? "تقرير عمليات السحب - إجمالي" : "تقرير عمليات السحب - تفصيلي";
  }

  function reportPeriodText() {
    return `فترة التقرير: من ${formatLocalWallDate(fromAt)} إلى ${formatLocalWallDate(toAt)}`;
  }

  function exportWithdrawalsExcel() {
    downloadExcel(reportMode === "summary" ? "withdrawal-summary-report.xls" : "withdrawal-detail-report.xls", currentReportTitle(), currentExportRows());
  }

  function exportWithdrawalsPdf() {
    printPdf(currentReportTitle(), [{ title: currentReportTitle(), rows: currentExportRows() }], [
      reportPeriodText(),
      `تاريخ الطباعة: ${formatApiDate(new Date())}`,
    ]);
  }

  const withdrawalTotalItems = Object.entries(withdrawalStats.amountByCurrency);
  const withdrawalTotalText = withdrawalTotalItems
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(" / ");

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">التقارير</h1>
          <div className="mt-1 text-sm text-slate-500">تقرير عمليات السحب من Journal.</div>
        </div>
      </div>

      <div className="mb-5 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-[minmax(160px,0.85fr)_minmax(180px,0.9fr)_minmax(200px,1fr)_minmax(240px,1.25fr)_minmax(170px,1fr)_minmax(170px,1fr)_minmax(120px,auto)]">
          <div className="flex h-11 overflow-hidden rounded-lg border border-slate-300 bg-slate-50 p-1 text-sm font-semibold">
            {[
              ["summary", "إجمالي"],
              ["detail", "تفصيلي"],
            ].map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  if (reportMode === mode) return;
                  setReportMode(mode);
                  resetReportData();
                }}
                className={`focus-ring flex-1 rounded-md px-3 transition ${
                  reportMode === mode ? "bg-teal-700 text-white shadow-sm" : "text-slate-600 hover:bg-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <select
            value={branchFilter}
            onChange={(event) => {
              setBranchFilter(event.target.value);
              resetReportData();
            }}
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
              onChange={(event) => {
                setAtmFilter(event.target.value);
                resetReportData();
              }}
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
              onChange={(event) => {
                setQuery(event.target.value);
                resetReportData();
              }}
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
                resetReportData();
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
                resetReportData();
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

      <div>
        <SectionHeader
          icon={CreditCard}
          title="تقرير عمليات السحب"
          meta={
            withdrawalsLoaded
              ? reportMode === "summary"
                ? `${withdrawalStats.total} عملية · إجمالي`
                : `${filteredWithdrawals.length} من ${withdrawalStats.total} عملية · تفصيلي`
              : "حدد الفترة ثم اضغط عرض السحب"
          }
          action={
            withdrawalsLoaded && withdrawalStats.total > 0 ? (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={exportWithdrawalsExcel}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
                >
                  <Download size={16} />
                  <span>Excel</span>
                </button>
                <button
                  type="button"
                  onClick={exportWithdrawalsPdf}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
                >
                  <Download size={16} />
                  <span>PDF</span>
                </button>
              </div>
            ) : null
          }
        />
        {withdrawalsError && <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{withdrawalsError}</div>}
        <div className="mb-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="إجمالي العمليات" value={withdrawalStats.total} icon={ClipboardList} />
          <StatCard label="ناجحة" value={withdrawalStats.completed} icon={CheckCircle2} tone="emerald" />
          <StatCard label="غير ناجحة" value={withdrawalStats.incomplete} icon={AlertTriangle} tone={withdrawalStats.incomplete ? "amber" : "emerald"} />
          <StatCard
            label="إجمالي السحب"
            value={
              withdrawalTotalItems.length ? (
                <div className="space-y-1">
                  {withdrawalTotalItems.map(([currency, amount]) => (
                    <div key={currency} className="flex items-baseline justify-between gap-3">
                      <span className="text-sm font-semibold text-sky-800">{currency}</span>
                      <span className="text-lg font-semibold tabular-nums text-slate-950">{Number(amount || 0).toLocaleString("en-US")}</span>
                    </div>
                  ))}
                </div>
              ) : (
                "-"
              )
            }
            icon={BarChart3}
            tone="sky"
            valueClassName="mt-2 text-base font-semibold leading-tight"
          />
        </div>
        {!withdrawalsLoaded ? (
          <EmptyPanel>لن يتم تحميل عمليات السحب قبل تحديد الفترة والضغط على عرض السحب.</EmptyPanel>
        ) : reportMode === "detail" ? (
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
            {withdrawalStats.total > filteredWithdrawals.length && (
              <div className="border-t border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                تم عرض أول {filteredWithdrawals.length} من أصل {withdrawalStats.total} عملية فقط. ضيّق الفترة أو اختر صرافاً محدداً لنتيجة أدق.
              </div>
            )}
          </TableShell>
        ) : null}
      </div>
    </section>
  );
}
