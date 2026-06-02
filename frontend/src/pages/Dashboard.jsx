import {
  Activity,
  AlertTriangle,
  Clock3,
  Cpu,
  Gauge,
  Monitor,
  RefreshCw,
  Router,
  ShieldAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiDate, formatLastSeenAge, isRecentlyOnline } from "../api/time";

function getModuleStatus(atm, moduleName) {
  return (atm.module_status_json && atm.module_status_json[moduleName]) || "-";
}

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

function SummaryTile({ label, value, tone = "slate", icon: Icon }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-950",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    rose: "border-rose-200 bg-rose-50 text-rose-900",
    teal: "border-teal-200 bg-teal-50 text-teal-900",
  };

  return (
    <div className={`rounded-lg border px-4 py-3 shadow-sm ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-slate-600">{label}</div>
        {Icon && <Icon size={19} className="text-current opacity-75" />}
      </div>
      <div className="mt-2 text-4xl font-semibold leading-none tracking-normal">{value}</div>
    </div>
  );
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

function ModulePill({ label, status }) {
  const normalized = String(status || "-").toLowerCase();
  const tone =
    normalized === "running" || normalized === "configured"
      ? "bg-emerald-50 text-emerald-700"
      : normalized === "error"
        ? "bg-rose-50 text-rose-700"
        : normalized === "disabled"
          ? "bg-slate-100 text-slate-600"
          : "bg-amber-50 text-amber-700";

  return (
    <span className={`inline-flex min-h-8 items-center justify-center rounded-full px-3 text-xs font-semibold ${tone}`}>
      {label}: {status || "-"}
    </span>
  );
}

function AtmMonitorCard({ atm }) {
  const health = getAtmHealth(atm);
  const HealthIcon = health.icon;
  const switchStatus = getSwitchStatus(atm);
  const lastProblem = atm.last_config_error || (hasRecentAgentError(atm) ? atm.last_agent_error : null) || atm.last_switch_probe_error;

  return (
    <article className={`relative overflow-hidden rounded-lg border p-4 shadow-sm ${health.shell}`}>
      <div className={`absolute inset-y-0 right-0 w-1.5 ${health.strip}`} />

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold text-slate-950">{atm.name}</span>
            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{atm.atm_id}</span>
          </div>
          <div className="mt-1 truncate text-sm text-slate-500">
            {atm.branch} · {atm.vpn_ip}
          </div>
        </div>

        <div className={`flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold ${health.pill}`}>
          <HealthIcon size={17} />
          <span>{health.title}</span>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <InfoLine label="آخر اتصال" value={formatLastSeenAge(atm)} tone={health.text} />
        <InfoLine label="Latency" value={getLatencyText(atm)} tone={getLatencyTone(atm)} />
        <InfoLine label="Agent" value={atm.agent_version || "-"} />
        <InfoLine
          label="Config"
          value={isPendingConfig(atm) ? `${atm.applied_config_version}/${atm.config_version}` : "Synced"}
          tone={isPendingConfig(atm) ? "text-amber-700" : "text-emerald-700"}
        />
        <InfoLine label="XFS" value={atm.xfs_profile === "grg" ? "GRG" : atm.xfs_profile === "custom" ? "Custom" : "NCR"} />
        <InfoLine label="Package" value={atm.current_package_version || atm.last_image_version || "-"} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <ModulePill label="Media" status={getModuleStatus(atm, "media_update")} />
        <ModulePill label="Cash" status={getModuleStatus(atm, "cash_monitoring")} />
        <span className={`inline-flex min-h-8 items-center gap-1 rounded-full px-3 text-xs font-semibold ${switchStatus.tone}`}>
          <Router size={14} />
          Switch: {switchStatus.label}
        </span>
      </div>

      {lastProblem && (
        <div className="mt-4 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-xs font-medium text-rose-700">
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
  const pending = packages.reduce((total, item) => total + (item.pending_targets || 0), 0);
  const failed = packages.reduce((total, item) => total + (item.failed_targets || 0), 0);
  const pendingConfig = atms.filter(isPendingConfig).length;
  const cashLow = cashSummary?.cash_low_atms || 0;
  const cashCritical = cashSummary?.cash_critical_atms || 0;
  const cashEmpty = cashSummary?.cash_empty_atms || 0;
  const cashStale = cashSummary?.cash_stale_atms || 0;
  const criticalCount = offline + failed + cashCritical + cashEmpty;

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
          <div className="flex items-center gap-2 text-sm font-semibold text-teal-700">
            <Monitor size={18} />
            <span>ATM Monitoring Wall</span>
          </div>
          <h1 className="mt-1 text-3xl font-semibold text-slate-950">لوحة المراقبة</h1>
          <p className="text-sm text-slate-500">عرض مباشر لحالة الصرافات والـ Agent والنقد والتحديثات</p>
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

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-6">
        <SummaryTile label="الصرافات" value={atms.length} icon={Monitor} />
        <SummaryTile label="Online" value={online} tone="emerald" icon={Wifi} />
        <SummaryTile label="Offline" value={offline} tone={offline ? "rose" : "emerald"} icon={WifiOff} />
        <SummaryTile label="Critical" value={criticalCount} tone={criticalCount ? "rose" : "emerald"} icon={ShieldAlert} />
        <SummaryTile label="Pending Config" value={pendingConfig} tone={pendingConfig ? "amber" : "emerald"} icon={Cpu} />
        <SummaryTile label="Pending / Failed" value={`${pending} / ${failed}`} tone={failed ? "rose" : pending ? "amber" : "slate"} icon={Activity} />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryTile label="Cash Low" value={cashLow} tone={cashLow ? "amber" : "emerald"} icon={Gauge} />
        <SummaryTile label="Cash Critical" value={cashCritical} tone={cashCritical ? "rose" : "emerald"} icon={AlertTriangle} />
        <SummaryTile label="Cash Empty" value={cashEmpty} tone={cashEmpty ? "rose" : "emerald"} icon={ShieldAlert} />
        <SummaryTile label="Cash Data Stale" value={cashStale} tone={cashStale ? "amber" : "emerald"} icon={Clock3} />
      </div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-950">الصرافات</h2>
      </div>

      <div className="mt-3 grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
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
