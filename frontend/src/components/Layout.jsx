import {
  Activity,
  Bell,
  BookOpenText,
  Boxes,
  Download,
  FileArchive,
  Landmark,
  Home,
  LogOut,
  MonitorCog,
  ScrollText,
  Settings,
  Upload,
  Users,
} from "lucide-react";

export const nav = [
  { id: "dashboard", label: "لوحة المراقبة", icon: Home },
  { id: "atms", label: "الصرافات", icon: MonitorCog },
  { id: "upload", label: "رفع حزمة الوسائط", icon: Upload },
  { id: "packages", label: "تحديثات الوسائط", icon: FileArchive },
  { id: "agent-updates", label: "تحديثات Agent", icon: Boxes },
  { id: "cash", label: "مراقبة النقد", icon: Landmark },
  { id: "notifications", label: "مركز التنبيهات", icon: Bell },
  { id: "agent-downloads", label: "Agent Downloads", icon: Download },
  { id: "logs", label: "السجلات", icon: ScrollText },
  { id: "journal", label: "Journal", icon: BookOpenText },
  { id: "settings", label: "الإعدادات", icon: Settings },
  { id: "users", label: "المستخدمون", icon: Users },
];

export default function Layout({ activePage, setActivePage, onLogout, allowedPages = [], children }) {
  const visibleNav = nav.filter((item) => allowedPages.includes(item.id));

  return (
    <div className="min-h-screen lg:flex" dir="rtl">
      <aside className="min-w-0 overflow-hidden border-b border-slate-200 bg-white lg:min-h-screen lg:w-72 lg:border-b-0 lg:border-l">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-4 sm:px-5 lg:py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white">
              <Activity size={22} />
            </div>
            <div className="min-w-0">
              <div className="truncate text-base font-semibold text-slate-950">QIB ATM</div>
              <div className="truncate text-xs text-slate-500">Manager</div>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="focus-ring inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 lg:hidden"
            title="تسجيل الخروج"
          >
            <LogOut size={18} />
          </button>
        </div>

        <nav className="flex max-w-full flex-wrap gap-2 px-3 py-2 lg:block lg:space-y-1 lg:p-3">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const selected = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActivePage(item.id)}
                className={`focus-ring flex min-h-10 min-w-fit items-center gap-2 rounded-lg px-3 py-2 text-sm transition lg:w-full ${
                  selected
                    ? "bg-teal-50 text-teal-800"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
                title={item.label}
              >
                <Icon size={18} className="shrink-0" />
                <span className="whitespace-nowrap">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="hidden border-t border-slate-200 p-3 lg:block">
          <button
            onClick={onLogout}
            className="focus-ring flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
            title="تسجيل الخروج"
          >
            <LogOut size={18} />
            <span>تسجيل الخروج</span>
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1800px] px-3 py-4 sm:px-6 sm:py-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
