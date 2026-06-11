import { useCallback, useEffect, useMemo, useState } from "react";
import { api, authExpiredEvent, clearAuthToken, getAuthToken } from "./api/client";
import Layout, { nav } from "./components/Layout";
import AgentDownloads from "./pages/AgentDownloads";
import AgentUpdates from "./pages/AgentUpdates";
import Atms from "./pages/Atms";
import CashMonitoring from "./pages/CashMonitoring";
import Dashboard from "./pages/Dashboard";
import Journal from "./pages/Journal";
import Login from "./pages/Login";
import Logs from "./pages/Logs";
import NotificationCenter from "./pages/NotificationCenter";
import Packages from "./pages/Packages";
import Settings from "./pages/Settings";
import UploadPackage from "./pages/UploadPackage";
import UserManagement from "./pages/UserManagement";

const fallbackPages = ["dashboard"];
const LOG_PAGE_SIZE = 50;

function AuthLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4" dir="rtl">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-5 text-center shadow-sm">
        <div className="mx-auto mb-3 h-10 w-10 animate-spin rounded-full border-4 border-teal-100 border-t-teal-700" />
        <div className="font-semibold text-slate-950">جاري التحقق من الجلسة</div>
      </div>
    </div>
  );
}

function BackgroundLoadingNotice() {
  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-teal-100 bg-teal-50 text-sm text-teal-800 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-teal-200 border-t-teal-700" />
          <span className="font-medium">جاري تحميل بيانات اللوحة</span>
        </div>
        <span className="text-xs text-teal-700">يمكنك استخدام النظام أثناء التحميل</span>
      </div>
      <div className="h-1 bg-teal-100">
        <div className="h-full w-full animate-pulse bg-teal-600" />
      </div>
    </div>
  );
}

function getAllowedPages(user) {
  const pageIds = nav.map((item) => item.id);
  const pages = Array.isArray(user?.allowed_pages) ? user.allowed_pages : fallbackPages;
  const allowed = new Set(pages);
  return pageIds.filter((page) => allowed.has(page));
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(() => Boolean(getAuthToken()));
  const [activePage, setActivePage] = useState("dashboard");
  const [atms, setAtms] = useState([]);
  const [packages, setPackages] = useState([]);
  const [packagesLoaded, setPackagesLoaded] = useState(false);
  const [packagesLoading, setPackagesLoading] = useState(false);
  const [cashSummary, setCashSummary] = useState(null);
  const [logs, setLogs] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [logsLoaded, setLogsLoaded] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsPage, setLogsPage] = useState(1);
  const [logsHasMore, setLogsHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [initialDataLoading, setInitialDataLoading] = useState(false);
  const [globalError, setGlobalError] = useState("");

  const refreshCore = useCallback(async () => {
    setLoading(true);
    setGlobalError("");
    try {
      const [atmData, cashData] = await Promise.all([
        api.listAtms(),
        api.getCashSummary({ includeDetails: false }),
      ]);
      setAtms(atmData);
      setCashSummary(cashData);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل البيانات");
      if (err.status === 401) {
        clearAuthToken();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLogsLegacy = useCallback(async (filters = {}) => {
    setLogsLoading(true);
    setGlobalError("");
    try {
      const source = filters.source || "all";
      const shouldLoadAgent = source === "all" || source === "agent";
      const shouldLoadAudit = source === "all" || source === "audit";
      const [agentLogData, auditLogData] = await Promise.all([
        shouldLoadAgent ? api.listLogs(filters) : Promise.resolve([]),
        shouldLoadAudit ? api.listAuditLogs(filters) : Promise.resolve([]),
      ]);
      setLogs(agentLogData);
      setAuditLogs(auditLogData);
      setLogsLoaded(true);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل السجلات");
    } finally {
      setLogsLoading(false);
    }
  }, []);

  const refreshLogs = useCallback(async (filters = {}, options = {}) => {
    setLogsLoading(true);
    setGlobalError("");
    try {
      const source = filters.source || "all";
      const pageSize = filters.pageSize || filters.limit || LOG_PAGE_SIZE;
      const page = options.page || filters.page || 1;
      const requestFilters = {
        ...filters,
        page,
        pageSize,
        limit: pageSize,
        level: filters.level === "all" ? "" : filters.level,
      };
      const append = Boolean(options.append);
      const shouldLoadAgent = source === "all" || source === "agent";
      const shouldLoadAudit = (source === "all" || source === "audit") && !requestFilters.level;
      const [agentLogData, auditLogData] = await Promise.all([
        shouldLoadAgent ? api.listLogs(requestFilters) : Promise.resolve([]),
        shouldLoadAudit ? api.listAuditLogs(requestFilters) : Promise.resolve([]),
      ]);

      setLogs((current) => {
        if (!shouldLoadAgent) return [];
        return append ? [...current, ...agentLogData] : agentLogData;
      });
      setAuditLogs((current) => {
        if (!shouldLoadAudit) return [];
        return append ? [...current, ...auditLogData] : auditLogData;
      });
      setLogsPage(page);
      setLogsHasMore((shouldLoadAgent && agentLogData.length >= pageSize) || (shouldLoadAudit && auditLogData.length >= pageSize));
      setLogsLoaded(true);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل السجلات");
    } finally {
      setLogsLoading(false);
    }
  }, []);

  const loadMoreLogs = useCallback(
    (filters = {}) => {
      if (logsLoading || !logsHasMore) return;
      refreshLogs(filters, { append: true, page: logsPage + 1 });
    },
    [logsHasMore, logsLoading, logsPage, refreshLogs],
  );

  const refreshPackages = useCallback(async () => {
    setPackagesLoading(true);
    setGlobalError("");
    try {
      const packageData = await api.listPackages();
      setPackages(packageData);
      setPackagesLoaded(true);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل الحزم");
      if (err.status === 401) {
        clearAuthToken();
        setUser(null);
      }
    } finally {
      setPackagesLoading(false);
    }
  }, []);

  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setInitialDataLoading(true);
    setGlobalError("");
    try {
      const [atmData, cashData] = await Promise.all([
        api.listAtms(),
        api.getCashSummary({ includeDetails: false }),
      ]);
      setAtms(atmData);
      setCashSummary(cashData);

    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل البيانات");
      if (err.status === 401) {
        clearAuthToken();
        setUser(null);
      }
    } finally {
      setLoading(false);
      setInitialDataLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setCheckingAuth(false);
      return undefined;
    }

    let active = true;
    setCheckingAuth(true);
    api
      .me()
      .then((currentUser) => {
        if (!active) return;
        setUser(currentUser);
        setCheckingAuth(false);
        loadInitialData();
      })
      .catch(() => {
        if (!active) return;
        clearAuthToken();
        setUser(null);
      })
      .finally(() => {
        if (active) setCheckingAuth(false);
      });

    return () => {
      active = false;
    };
  }, [loadInitialData]);

  const allowedPages = useMemo(() => getAllowedPages(user), [user]);
  const visiblePage = allowedPages.includes(activePage) ? activePage : allowedPages[0] || "dashboard";

  useEffect(() => {
    function handleAuthExpired(event) {
      setUser(null);
      setCheckingAuth(false);
      setGlobalError(event.detail?.message || "انتهت الجلسة. سجّل الدخول مرة أخرى.");
    }

    window.addEventListener(authExpiredEvent, handleAuthExpired);
    return () => window.removeEventListener(authExpiredEvent, handleAuthExpired);
  }, []);

  useEffect(() => {
    if (user && activePage !== visiblePage) {
      setActivePage(visiblePage);
    }
  }, [activePage, user, visiblePage]);

  useEffect(() => {
    if (user && visiblePage === "logs" && !logsLoaded) {
      refreshLogs({ source: "agent", pageSize: LOG_PAGE_SIZE });
    }
  }, [logsLoaded, refreshLogs, user, visiblePage]);

  useEffect(() => {
    if (user && visiblePage === "packages" && !packagesLoaded && !packagesLoading) {
      refreshPackages();
    }
  }, [packagesLoaded, packagesLoading, refreshPackages, user, visiblePage]);

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Local logout should still complete if the server session is already expired.
    }
    clearAuthToken();
    setUser(null);
    setCheckingAuth(false);
  }

  if (checkingAuth) {
    return <AuthLoading />;
  }

  if (!user) {
    return (
      <Login
        initialError={globalError}
        onLogin={(loggedInUser) => {
          setUser(loggedInUser);
          setGlobalError("");
          setCheckingAuth(false);
          loadInitialData();
        }}
      />
    );
  }

  let page = null;
  if (visiblePage === "dashboard") page = <Dashboard atms={atms} cashSummary={cashSummary} loading={loading} onRefresh={refreshCore} />;
  if (visiblePage === "atms") page = <Atms atms={atms} onChanged={refreshCore} />;
  if (visiblePage === "upload") {
    page = (
      <UploadPackage
        onUploaded={() => {
          setPackagesLoaded(false);
          refreshPackages();
        }}
        onOpenPackages={() => setActivePage("packages")}
      />
    );
  }
  if (visiblePage === "packages") page = <Packages packages={packages} atms={atms} onChanged={refreshPackages} />;
  if (visiblePage === "agent-updates") page = <AgentUpdates atms={atms} />;
  if (visiblePage === "cash") page = <CashMonitoring atms={atms} />;
  if (visiblePage === "notifications") page = <NotificationCenter />;
  if (visiblePage === "agent-downloads") page = <AgentDownloads />;
  if (visiblePage === "logs") {
    page = (
      <Logs
        logs={logs}
        auditLogs={auditLogs}
        atms={atms}
        loading={logsLoading}
        hasMore={logsHasMore}
        onRefresh={refreshLogs}
        onLoadMore={loadMoreLogs}
      />
    );
  }
  if (visiblePage === "journal") page = <Journal atms={atms} />;
  if (visiblePage === "settings") {
    page = <Settings atms={atms} onChanged={refreshCore} onOpenAgentDownloads={() => setActivePage("agent-downloads")} />;
  }
  if (visiblePage === "users") page = <UserManagement currentUser={user} />;

  return (
    <Layout activePage={visiblePage} setActivePage={setActivePage} onLogout={logout} allowedPages={allowedPages}>
      {initialDataLoading && <BackgroundLoadingNotice />}
      {globalError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {globalError}
        </div>
      )}
      {page}
    </Layout>
  );
}
