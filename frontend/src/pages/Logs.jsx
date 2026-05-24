import { RefreshCw } from "lucide-react";

export default function Logs({ logs, auditLogs, onRefresh }) {
  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">Logs</h1>
          <p className="text-sm text-slate-500">سجلات الـ Agent وسجل التدقيق</p>
        </div>
        <button
          onClick={onRefresh}
          className="focus-ring flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50"
          title="تحديث السجلات"
        >
          <RefreshCw size={17} />
          <span>تحديث</span>
        </button>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">Agent Logs</div>
          <div className="max-h-[640px] divide-y divide-slate-100 overflow-auto">
            {logs.map((log) => (
              <div key={log.id} className="px-4 py-3 text-sm">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{log.atm?.atm_id || "-"}</span>
                  <span className="text-xs text-slate-500">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <div className={log.level === "error" ? "text-rose-700" : "text-slate-700"}>{log.message}</div>
              </div>
            ))}
            {logs.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا توجد سجلات</div>}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3 font-medium">Audit Logs</div>
          <div className="max-h-[640px] divide-y divide-slate-100 overflow-auto">
            {auditLogs.map((log) => (
              <div key={log.id} className="px-4 py-3 text-sm">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{log.action}</span>
                  <span className="text-xs text-slate-500">{new Date(log.created_at).toLocaleString()}</span>
                </div>
                <div className="text-slate-600">{log.actor_type}: {log.actor_id || "-"}</div>
              </div>
            ))}
            {auditLogs.length === 0 && <div className="px-4 py-8 text-center text-sm text-slate-500">لا يوجد سجل تدقيق</div>}
          </div>
        </div>
      </div>
    </section>
  );
}

