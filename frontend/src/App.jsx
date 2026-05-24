import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import Layout, { nav } from "./components/Layout";
import AgentDownloads from "./pages/AgentDownloads";
import Atms from "./pages/Atms";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Logs from "./pages/Logs";
import Packages from "./pages/Packages";
import Settings from "./pages/Settings";
import UploadPackage from "./pages/UploadPackage";
import UserManagement from "./pages/UserManagement";

const fallbackPages = ["dashboard"];

function getAllowedPages(user) {
  const pageIds = nav.map((item) => item.id);
  const pages = Array.isArray(user?.allowed_pages) ? user.allowed_pages : fallbackPages;
  return pages.filter((page) => pageIds.includes(page));
}

export default function App() {
  const [user, setUser] = useState(null);
  const [activePage, setActivePage] = useState("dashboard");
  const [atms, setAtms] = useState([]);
  const [packages, setPackages] = useState([]);
  const [logs, setLogs] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [globalError, setGlobalError] = useState("");

  const refreshCore = useCallback(async () => {
    setLoading(true);
    setGlobalError("");
    try {
      const [atmData, packageData] = await Promise.all([api.listAtms(), api.listPackages()]);
      setAtms(atmData);
      setPackages(packageData);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل البيانات");
      if (err.status === 401) {
        localStorage.removeItem("atm_media_token");
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLogs = useCallback(async () => {
    setGlobalError("");
    try {
      const [agentLogData, auditLogData] = await Promise.all([api.listLogs(), api.listAuditLogs()]);
      setLogs(agentLogData);
      setAuditLogs(auditLogData);
    } catch (err) {
      setGlobalError(err.message || "تعذر تحميل السجلات");
    }
  }, []);

  useEffect(() => {
    if (localStorage.getItem("atm_media_token")) {
      api
        .me()
        .then((currentUser) => {
          setUser(currentUser);
          refreshCore();
          refreshLogs();
        })
        .catch(() => {
          localStorage.removeItem("atm_media_token");
          setUser(null);
        });
    }
  }, [refreshCore, refreshLogs]);

  const allowedPages = useMemo(() => getAllowedPages(user), [user]);
  const visiblePage = allowedPages.includes(activePage) ? activePage : allowedPages[0] || "dashboard";

  useEffect(() => {
    if (user && activePage !== visiblePage) {
      setActivePage(visiblePage);
    }
  }, [activePage, user, visiblePage]);

  function logout() {
    localStorage.removeItem("atm_media_token");
    setUser(null);
  }

  if (!user && !localStorage.getItem("atm_media_token")) {
    return <Login onLogin={(loggedInUser) => { setUser(loggedInUser); refreshCore(); refreshLogs(); }} />;
  }

  let page = null;
  if (visiblePage === "dashboard") page = <Dashboard atms={atms} packages={packages} loading={loading} onRefresh={refreshCore} />;
  if (visiblePage === "atms") page = <Atms atms={atms} onChanged={refreshCore} />;
  if (visiblePage === "upload") page = <UploadPackage onUploaded={refreshCore} onOpenPackages={() => setActivePage("packages")} />;
  if (visiblePage === "packages") page = <Packages packages={packages} atms={atms} onChanged={refreshCore} />;
  if (visiblePage === "agent-downloads") page = <AgentDownloads />;
  if (visiblePage === "logs") page = <Logs logs={logs} auditLogs={auditLogs} onRefresh={refreshLogs} />;
  if (visiblePage === "settings") page = <Settings onOpenAgentDownloads={() => setActivePage("agent-downloads")} />;
  if (visiblePage === "users") page = <UserManagement currentUser={user} />;

  return (
    <Layout activePage={visiblePage} setActivePage={setActivePage} onLogout={logout} allowedPages={allowedPages}>
      {globalError && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {globalError}
        </div>
      )}
      {page}
    </Layout>
  );
}
