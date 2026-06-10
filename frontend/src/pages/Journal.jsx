import {
  AlertTriangle,
  Banknote,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  CreditCard,
  FileText,
  RefreshCw,
  Search,
  TerminalSquare,
  TimerReset,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { formatApiDate, formatLocalWallDate } from "../api/time";

const eventTypeOptions = [
  ["all", "كل الأحداث"],
  ["TRANSACTION_END", "عمليات"],
  ["DISPENSE_SUCCESS", "Dispense"],
  ["MONEY_TAKEN", "Money taken"],
  ["TAKE_CASH_TIMEOUT", "Timeout"],
  ["CASSETTE_OUT", "Cassette"],
  ["ENTER_OUTOFSERVICE_MODE", "Out of service"],
  ["ENTER_INSERVICE_MODE", "In service"],
  ["LINE_DOWN", "Line down"],
  ["LINE_UP", "Line up"],
  ["PRINTER_EVENT", "Printer"],
];

const limitOptions = [100, 200, 300];

function normalizeText(value) {
  return String(value || "").toLowerCase().trim();
}

function compactAmount(event) {
  if (!event?.amount) return "";
  return `${event.amount} ${event.currency || ""}`.trim();
}

function eventTitle(eventType) {
  return String(eventType || "Journal event").replaceAll("_", " ").toLowerCase();
}

function eventTone(event) {
  const severity = normalizeText(event?.severity);
  if (severity === "error") return "border-rose-200 bg-rose-50 text-rose-800";
  if (severity === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  if (event?.event_type === "TRANSACTION_END" && event?.details_json?.completed === true) {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  return "border-slate-200 bg-white text-slate-800";
}

function cassetteText(items) {
  if (!Array.isArray(items) || items.length === 0) return "";
  return items
    .map((item) => `CAS ${item.cassette_no}: ${item.out} ورقة, reject ${item.reject}, deno ${item.denomination}`)
    .join(" | ");
}

function eventSearchText(event) {
  return [
    event.event_type,
    event.message,
    event.transaction_serial,
    event.transaction_type,
    event.amount,
    event.currency,
    event.rrn,
    event.stan,
    event.auth_code,
    event.card_masked,
    event.receipt_date,
    event.file_path,
    cassetteText(event.cassette_outputs_json),
  ].join(" ");
}

function StatBox({ label, value, icon: Icon, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-950",
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    rose: "border-rose-200 bg-rose-50 text-rose-950",
    sky: "border-sky-200 bg-sky-50 text-sky-950",
  };

  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <Icon size={18} className="opacity-70" />
      </div>
      <div className="mt-2 text-2xl font-semibold leading-none">{value}</div>
    </div>
  );
}

function EmptyState({ hasAtm, waitingForLoad = false }) {
  const title = !hasAtm ? "اختر صرافًا" : waitingForLoad ? "جاهز للتحميل" : "لا توجد نتائج مطابقة";
  const subtitle = !hasAtm
    ? "لن يتم تحميل Journal قبل تحديد الصراف المطلوب."
    : waitingForLoad
      ? "اضغط تحميل Journal لعرض الأحداث الخاصة بالصراف والفترة المحددة."
      : "غيّر الفترة أو نوع الحدث ثم اضغط تحميل Journal.";

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-12 text-center">
      <ClipboardList className="mx-auto text-slate-400" size={30} />
      <div className="mt-3 font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm text-slate-500">{subtitle}</div>
    </div>
  );
}

function TransactionCard({ event }) {
  const details = event.details_json || {};
  const amount = compactAmount(event);
  const completed = details.completed === true;
  const timeout = details.take_cash_timeout === true;
  const cassettes = cassetteText(event.cassette_outputs_json);

  return (
    <article className={`rounded-lg border p-4 shadow-sm ${completed ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-950">{event.transaction_type || "Transaction"}</span>
            {completed && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
                <CheckCircle2 size={12} />
                مكتملة
              </span>
            )}
            {timeout && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                <AlertTriangle size={12} />
                Timeout
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-slate-600">{formatLocalWallDate(event.occurred_at)}</div>
        </div>
        {amount && <div className="text-left text-lg font-semibold text-slate-950">{amount}</div>}
      </div>

      <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
        {event.rrn && <Info label="RRN" value={event.rrn} />}
        {event.stan && <Info label="STAN" value={event.stan} />}
        {event.auth_code && <Info label="Auth" value={event.auth_code} />}
        {event.card_masked && <Info label="Card" value={event.card_masked} />}
      </div>

      {cassettes && <div className="mt-3 rounded-lg bg-white px-3 py-2 text-xs text-slate-600">{cassettes}</div>}
    </article>
  );
}

function Info({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 break-words font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function EventRow({ event }) {
  const amount = compactAmount(event);
  const details = event.details_json || {};
  const cassettes = cassetteText(event.cassette_outputs_json);

  return (
    <article className={`rounded-lg border px-4 py-3 shadow-sm ${eventTone(event)}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-slate-950">{eventTitle(event.event_type)}</span>
            {event.transaction_serial && (
              <span className="rounded-full bg-white px-2 py-0.5 font-mono text-xs text-slate-600">SN {event.transaction_serial}</span>
            )}
            {details.completed === true && (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">completed</span>
            )}
          </div>
          <div className="mt-1 text-sm text-slate-700">{event.message}</div>
        </div>
        <div className="text-xs text-slate-500 md:text-left">
          <div>{formatLocalWallDate(event.occurred_at)}</div>
          <div className="mt-1">{event.severity}</div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
        {amount && <span className="rounded-full bg-white px-2 py-1">{amount}</span>}
        {event.rrn && <span className="rounded-full bg-white px-2 py-1">RRN {event.rrn}</span>}
        {event.stan && <span className="rounded-full bg-white px-2 py-1">STAN {event.stan}</span>}
        {event.card_masked && <span className="rounded-full bg-white px-2 py-1">{event.card_masked}</span>}
        {event.receipt_date && <span className="rounded-full bg-white px-2 py-1">Receipt {event.receipt_date}</span>}
      </div>

      {(cassettes || event.file_path) && (
        <details className="mt-3">
          <summary className="focus-ring inline-flex cursor-pointer list-none rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
            التفاصيل
          </summary>
          <div className="mt-2 grid gap-2 rounded-lg bg-white p-3 text-sm sm:grid-cols-3">
            {cassettes && <Info label="Cassette outputs" value={cassettes} />}
            {event.file_path && <Info label="File" value={event.file_path} />}
            {event.line_number && <Info label="Line" value={event.line_number} />}
            {event.received_at && <Info label="Received" value={formatApiDate(event.received_at)} />}
          </div>
        </details>
      )}
    </article>
  );
}

export default function Journal({ atms }) {
  const [atmId, setAtmId] = useState("");
  const [fromAt, setFromAt] = useState("");
  const [toAt, setToAt] = useState("");
  const [eventType, setEventType] = useState("all");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(200);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loadedAtm, setLoadedAtm] = useState("");
  const [loadedFilterKey, setLoadedFilterKey] = useState("");

  const selectedAtm = useMemo(() => (Array.isArray(atms) ? atms.find((atm) => atm.atm_id === atmId) : null), [atms, atmId]);
  const currentFilterKey = useMemo(() => JSON.stringify({ atmId, fromAt, toAt, limit }), [atmId, fromAt, limit, toAt]);
  const hasLoadedCurrentFilters = Boolean(loadedAtm && loadedFilterKey === currentFilterKey);

  async function loadJournal() {
    if (!atmId) {
      setEvents([]);
      setLoadedAtm("");
      setLoadedFilterKey("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await api.listJournalLogs({ atmId, fromAt, toAt, limit });
      setEvents(Array.isArray(data) ? data : []);
      setLoadedAtm(atmId);
      setLoadedFilterKey(currentFilterKey);
    } catch (err) {
      setError(err.message || "تعذر تحميل Journal");
    } finally {
      setLoading(false);
    }
  }

  const filteredEvents = useMemo(() => {
    if (!hasLoadedCurrentFilters) return [];
    const needle = normalizeText(query);
    return events.filter((event) => {
      if (eventType !== "all" && event.event_type !== eventType) return false;
      if (!needle) return true;
      return normalizeText(eventSearchText(event)).includes(needle);
    });
  }, [events, eventType, hasLoadedCurrentFilters, query]);

  const stats = useMemo(() => {
    const transactions = filteredEvents.filter((event) => event.event_type === "TRANSACTION_END");
    const completed = transactions.filter((event) => event.details_json?.completed === true);
    const warnings = filteredEvents.filter((event) => normalizeText(event.severity) === "warning" || event.details_json?.take_cash_timeout);
    const totalAmount = completed.reduce((sum, event) => sum + (Number(event.amount) || 0), 0);
    return {
      total: filteredEvents.length,
      transactions: transactions.length,
      completed: completed.length,
      warnings: warnings.length,
      totalAmount,
    };
  }, [filteredEvents]);

  const transactions = useMemo(
    () => filteredEvents.filter((event) => event.event_type === "TRANSACTION_END").slice(0, 20),
    [filteredEvents],
  );

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">Journal</h1>
          {selectedAtm && (
            <div className="mt-1 text-sm text-slate-500">
              {selectedAtm.name || `ATM ${selectedAtm.atm_id}`} {selectedAtm.branch ? `- ${selectedAtm.branch}` : ""}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={loadJournal}
          disabled={loading || !atmId}
          className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          <span>تحميل Journal</span>
        </button>
      </div>

      <div className="mb-5 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[minmax(240px,1.4fr)_minmax(180px,1fr)_minmax(180px,1fr)_minmax(160px,0.8fr)_minmax(120px,0.6fr)]">
          <label className="relative block">
            <TerminalSquare className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <select
              value={atmId}
              onChange={(event) => {
                setAtmId(event.target.value);
                setEvents([]);
                setLoadedAtm("");
                setLoadedFilterKey("");
                setError("");
              }}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
            >
              <option value="">اختر الصراف</option>
              {(Array.isArray(atms) ? atms : []).map((atm) => (
                <option key={atm.atm_id} value={atm.atm_id}>
                  {atm.name ? `${atm.name} - ATM ${atm.atm_id}` : `ATM ${atm.atm_id}`}
                </option>
              ))}
            </select>
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={fromAt}
              onChange={(event) => setFromAt(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="From"
            />
          </label>

          <label className="relative block">
            <CalendarDays className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input
              type="datetime-local"
              value={toAt}
              onChange={(event) => setToAt(event.target.value)}
              className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
              title="To"
            />
          </label>

          <select
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            className="focus-ring min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {eventTypeOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          <select
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            className="focus-ring min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {limitOptions.map((value) => (
              <option key={value} value={value}>
                {value} سجل
              </option>
            ))}
          </select>
        </div>

        <label className="relative mt-3 block">
          <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="focus-ring min-h-11 w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-10 text-sm"
            placeholder="بحث بالعملية، RRN، STAN، البطاقة، الملف أو الكاسيت"
          />
        </label>
      </div>

      {error && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatBox label="الأحداث" value={stats.total} icon={ClipboardList} />
        <StatBox label="العمليات" value={stats.transactions} icon={FileText} tone="sky" />
        <StatBox label="مكتملة" value={stats.completed} icon={CheckCircle2} tone="emerald" />
        <StatBox label="تحذيرات" value={stats.warnings} icon={TimerReset} tone={stats.warnings ? "amber" : "emerald"} />
        <StatBox label="إجمالي السحب" value={stats.totalAmount ? stats.totalAmount.toLocaleString("en-US") : "-"} icon={Banknote} tone="sky" />
      </div>

      {!hasLoadedCurrentFilters && <EmptyState hasAtm={Boolean(atmId)} waitingForLoad={Boolean(atmId)} />}

      {hasLoadedCurrentFilters && transactions.length > 0 && (
        <div className="mb-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
            <CreditCard size={18} />
            <span>آخر العمليات</span>
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            {transactions.map((event) => (
              <TransactionCard key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}

      {hasLoadedCurrentFilters && (
        <div className="grid gap-3">
          {filteredEvents.length === 0 ? <EmptyState hasAtm /> : filteredEvents.map((event) => <EventRow key={event.id} event={event} />)}
        </div>
      )}
    </section>
  );
}
