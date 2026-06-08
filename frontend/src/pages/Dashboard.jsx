import {
  AlertTriangle,
  Clock3,
  Gauge,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiDate, formatLastSeenAge, isRecentlyOnline } from "../api/time";

function isPendingConfig(atm) {
  return (atm.applied_config_version || 0) < (atm.config_version || 0);
}

function getLatencyText(atm) {
  if (!isRecentlyOnline(atm) || !Number.isFinite(atm.latency_ms)) return "-";
  return `${atm.latency_ms} ms`;
}

function getLatencyTone(atm) {
  if (!isRecentlyOnline(atm) || !Number.isFinite(atm.latency_ms)) return "text-slate-500";
  if (atm.latency_ms <= 100) return "text-emerald-700";
  if (atm.latency_ms <= 300) return "text-amber-700";
  return "text-rose-700";
}

function getSwitchStatus(atm) {
  if (!atm.last_switch_probe_status) return { label: "لم يفحص", tone: "bg-slate-100 text-slate-600" };
  if (atm.last_switch_probe_status === "success") {
    return { label: `${atm.last_switch_probe_latency_ms ?? "-"} ms`, tone: "bg-emerald-50 text-emerald-700" };
  }
  if (atm.last_switch_probe_status === "failed") return { label: "فشل", tone: "bg-rose-50 text-rose-700" };
  return { label: "جاري", tone: "bg-amber-50 text-amber-700" };
}

function hasRecentAgentError(atm) {
  if (!atm.last_agent_error_at) return false;
  const timestamp = new Date(atm.last_agent_error_at).getTime();
  if (!Number.isFinite(timestamp)) return false;
  return Date.now() - timestamp <= 10 * 60 * 1000;
}

function getAtmHealth(atm) {
  const online = isRecentlyOnline(atm);
  const moduleStatuses = atm.module_status_json || {};
  const hasModuleError = Object.values(moduleStatuses).some((status) => String(status).toLowerCase() === "error");
  const recentAgentError = hasRecentAgentError(atm);

  if (!online) {
    return {
      rank: 0,
      label: "Offline",
      title: "غير متصل",
      icon: WifiOff,
      shell: "border-rose-300 bg-rose-50",
      strip: "bg-rose-600",
      pill: "bg-rose-100 text-rose-700",
      text: "text-rose-900",
    };
  }

  if (atm.last_config_error || recentAgentError || hasModuleError) {
    return {
      rank: 1,
      label: "Error",
      title: "خطأ",
      icon: ShieldAlert,
      shell: "border-rose-200 bg-white",
      strip: "bg-rose-500",
      pill: "bg-rose-50 text-rose-700",
      text: "text-rose-800",
    };
  }

  if (isPendingConfig(atm) || atm.last_switch_probe_status === "failed") {
    return {
      rank: 2,
      label: "Warning",
      title: "تنبيه",
      icon: AlertTriangle,
      shell: "border-amber-200 bg-white",
      strip: "bg-amber-500",
      pill: "bg-amber-50 text-amber-700",
      text: "text-amber-800",
    };
  }

  return {
    rank: 3,
    label: "Online",
    title: "متصل",
    icon: Wifi,
    shell: "border-emerald-200 bg-white",
    strip: "bg-emerald-600",
    pill: "bg-emerald-50 text-emerald-700",
    text: "text-emerald-800",
  };
}

function SummaryTile({ label, value, note = "", tone = "slate", icon: Icon, children }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    teal: "border-teal-200 bg-teal-50 text-teal-900",
  };

  return (
    <div className={`group relative rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`} tabIndex={children ? 0 : undefined}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-slate-600">{label}</div>
        {Icon && <Icon size={19} className="text-current opacity-75" />}
      </div>
      <div className="mt-2 text-3xl font-semibold leading-none tracking-normal sm:text-4xl">{value}</div>
      {note && <div className="mt-1 truncate text-xs font-medium text-slate-500">{note}</div>}
      {children && (
        <div className="absolute right-0 top-full z-30 mt-2 hidden w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-slate-200 bg-white p-3 text-slate-900 shadow-xl group-hover:block group-focus:block">
          {children}
        </div>
      )}
    </div>
  );
}

function CashRiskDetails({
  items = [],
  count = 0,
  title = "صرافات على وشك الانتهاء",
  emptyText = "لا توجد صرافات منخفضة النقد حالياً.",
  pendingText = "توجد صرافات منخفضة، لكن تفاصيلها لم تصل بعد. حدّث البيانات أو أعد تشغيل backend.",
  tone = "amber",
}) {
  const toneClasses = {
    amber: {
      item: "bg-amber-50",
      badge: "text-amber-800 ring-amber-200",
    },
    rose: {
      item: "bg-rose-50",
      badge: "text-rose-800 ring-rose-200",
    },
  };
  const classes = toneClasses[tone] || toneClasses.amber;

  if (!items.length) {
    return <div className="text-sm text-slate-500">{count > 0 ? pendingText : emptyText}</div>;
  }

  return (
    <div>
      <div className="mb-2 text-sm font-semibold text-slate-950">{title}</div>
      <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
        {items.slice(0, 10).map((item) => (
          <div key={`${item.atm_id}-${item.cassette_no}`} className={`rounded-lg px-3 py-2 text-sm ${classes.item}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-950">{item.name}</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {item.atm_id} · {item.branch} · Cassette {item.cassette_no}
                </div>
              </div>
              <span className={`shrink-0 rounded-full bg-white px-2 py-1 text-xs font-semibold ring-1 ${classes.badge}`}>
                {item.current_count}/{item.threshold_count}
              </span>
            </div>
            <div className="mt-1 text-xs text-slate-600">
              {item.currency} {item.denomination} · آخر قراءة {formatApiDate(item.read_at)}
            </div>
          </div>
        ))}
      </div>
      {items.length > 10 && <div className="mt-2 text-xs text-slate-500">و {items.length - 10} صناديق أخرى</div>}
    </div>
  );
}

function fallbackCashRiskDetails(cashSummary, atms, mode = "low") {
  const atmsByInternalId = new Map(atms.map((atm) => [Number(atm.id), atm]));
  const details = [];
  (cashSummary?.units || []).forEach((unit) => {
    const current = Number(unit.current_count);
    const low = Number(unit.low_threshold);
    if (!Number.isFinite(current)) return;
    if (mode === "empty") {
      if (current > 0) return;
    } else if (!Number.isFinite(low) || current > low) {
      return;
    }
    const atm = atmsByInternalId.get(Number(unit.atm_id));
    if (!atm) return;
    const threshold = mode === "empty" ? Number(unit.critical_threshold || unit.low_threshold || 1) : low;
    const ratio = threshold > 0 ? current / threshold : current;
    details.push({
      _ratio: ratio,
      atm_id: atm.atm_id,
      name: atm.name,
      branch: atm.branch,
      cassette_no: unit.cassette_no,
      currency: unit.expected_currency || unit.reported_currency || "",
      denomination: unit.expected_denomination || unit.reported_denomination || 0,
      current_count: current,
      threshold_count: threshold,
      status: unit.status,
      read_at: unit.read_at,
    });
  });
  return details
    .sort(
      (first, second) =>
        first._ratio - second._ratio ||
        String(first.atm_id).localeCompare(String(second.atm_id), "ar") ||
        Number(first.cassette_no) - Number(second.cassette_no),
    )
    .map(({ _ratio, ...item }) => item);
}

function InfoLine({ label, value, tone = "text-slate-900" }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] font-medium uppercase tracking-normal text-slate-500">{label}</div>
      <div className={`mt-0.5 truncate text-sm font-semibold ${tone}`} title={String(value || "-")}>
        {value || "-"}
      </div>
    </div>
  );
}

function AtmMonitorCard({ atm }) {
  const health = getAtmHealth(atm);
  const HealthIcon = health.icon;
  const switchStatus = getSwitchStatus(atm);
  const lastProblem = atm.last_config_error || (hasRecentAgentError(atm) ? atm.last_agent_error : null) || atm.last_switch_probe_error;

  return (
    <article className={`relative overflow-hidden rounded-lg border p-3 shadow-sm ${health.shell}`}>
      <div className={`absolute inset-y-0 right-0 w-1 ${health.strip}`} />

      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-base font-semibold text-slate-950">{atm.name}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{atm.atm_id}</span>
          </div>
          <div className="mt-0.5 truncate text-xs text-slate-500">
            {atm.branch} · {atm.vpn_ip}
          </div>
        </div>

        <div className={`flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${health.pill}`}>
          <HealthIcon size={14} />
          <span>{health.title}</span>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
        <InfoLine label="آخر اتصال" value={formatLastSeenAge(atm)} tone={health.text} />
        <InfoLine label="Latency" value={getLatencyText(atm)} tone={getLatencyTone(atm)} />
        <InfoLine
          label="Config"
          value={isPendingConfig(atm) ? `${atm.applied_config_version}/${atm.config_version}` : "Synced"}
          tone={isPendingConfig(atm) ? "text-amber-700" : "text-emerald-700"}
        />
        <InfoLine
          label="Switch"
          value={switchStatus.label}
          tone={
            switchStatus.tone.includes("rose")
              ? "text-rose-700"
              : switchStatus.tone.includes("amber")
                ? "text-amber-700"
                : "text-emerald-700"
          }
        />
      </div>

      {lastProblem && (
        <div className="mt-2 rounded-lg border border-rose-100 bg-rose-50 px-2 py-1.5 text-xs font-medium text-rose-700">
          <div className="truncate" title={lastProblem}>
            {lastProblem}
          </div>
        </div>
      )}
    </article>
  );
}

export default function Dashboard({ atms, packages, cashSummary, loading, onRefresh }) {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdatedAt, setLastUpdatedAt] = useState(new Date());

  const online = atms.filter(isRecentlyOnline).length;
  const offline = atms.length - online;
  const cashLowAtms = cashSummary?.cash_low_atms || 0;
  const cashEmptyAtms = cashSummary?.cash_empty_atms || 0;
  const cashLowDetails = (cashSummary?.low_cash_atms || []).length
    ? cashSummary.low_cash_atms
    : fallbackCashRiskDetails(cashSummary, atms, "low");
  const cashEmptyDetails = (cashSummary?.empty_cash_atms || []).length
    ? cashSummary.empty_cash_atms
    : fallbackCashRiskDetails(cashSummary, atms, "empty");
  const cashLow = cashSummary?.cash_low_units ?? cashLowDetails.length ?? cashLowAtms;
  const cashEmpty = cashSummary?.cash_empty_units ?? cashEmptyDetails.length ?? cashEmptyAtms;

  const sortedAtms = useMemo(
    () =>
      [...atms].sort((first, second) => {
        const firstHealth = getAtmHealth(first);
        const secondHealth = getAtmHealth(second);
        if (firstHealth.rank !== secondHealth.rank) return firstHealth.rank - secondHealth.rank;
        return String(first.atm_id).localeCompare(String(second.atm_id), "ar");
      }),
    [atms],
  );

  useEffect(() => {
    setLastUpdatedAt(new Date());
  }, [atms, packages, cashSummary]);

  useEffect(() => {
    if (!autoRefresh) return undefined;
    const timer = window.setInterval(() => {
      if (!loading) onRefresh();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loading, onRefresh]);

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">لوحة المراقبة</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
            آخر تحديث: {formatApiDate(lastUpdatedAt)}
          </div>
          <button
            onClick={() => setAutoRefresh((current) => !current)}
            className={`focus-ring flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
              autoRefresh ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-300 bg-white text-slate-700"
            }`}
            title="تحديث تلقائي"
          >
            <Clock3 size={17} />
            <span>{autoRefresh ? "Auto 30s" : "Auto Off"}</span>
          </button>
          <button
            onClick={onRefresh}
            className="focus-ring flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50"
            title="تحديث البيانات"
          >
            <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "جار التحديث" : "تحديث"}</span>
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryTile label="Online" value={online} tone="emerald" icon={Wifi} />
        <SummaryTile label="Offline" value={offline} tone={offline ? "rose" : "emerald"} icon={WifiOff} />
        <SummaryTile
          label="Cash Low"
          value={cashLow}
          note={cashLowAtms ? `${cashLowAtms} صرافات` : ""}
          tone={cashLow ? "amber" : "emerald"}
          icon={Gauge}
        >
          <CashRiskDetails
            items={cashLowDetails}
            count={cashLow}
            title={`صناديق منخفضة${cashLowAtms ? ` في ${cashLowAtms} صرافات` : ""}`}
          />
        </SummaryTile>
        <SummaryTile
          label="Cash Empty"
          value={cashEmpty}
          note={cashEmptyAtms ? `${cashEmptyAtms} صرافات` : ""}
          tone={cashEmpty ? "rose" : "emerald"}
          icon={ShieldAlert}
        >
          <CashRiskDetails
            items={cashEmptyDetails}
            count={cashEmpty}
            title={`صناديق نفد منها النقد${cashEmptyAtms ? ` في ${cashEmptyAtms} صرافات` : ""}`}
            emptyText="لا توجد صرافات فارغة النقد حالياً."
            pendingText="توجد صرافات فارغة، لكن تفاصيلها لم تصل بعد. حدّث البيانات أو أعد تشغيل backend."
            tone="rose"
          />
        </SummaryTile>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-950">الصرافات</h2>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
        {sortedAtms.map((atm) => (
          <AtmMonitorCard key={atm.atm_id} atm={atm} />
        ))}
      </div>

      {atms.length === 0 && (
        <div className="mt-6 rounded-lg border border-slate-200 bg-white px-4 py-12 text-center text-sm text-slate-500">
          لا توجد صرافات بعد
        </div>
      )}
    </section>
  );
}
