import {
  Activity,
  Download,
  FileArchive,
  Home,
  LogOut,
  MonitorCog,
  ScrollText,
  Settings,
  Upload,
  Users,
} from "lucide-react";

export const nav = [
  { id: "dashboard", label: "لوحة التحكم", icon: Home },
  { id: "atms", label: "الصرافات", icon: MonitorCog },
  { id: "upload", label: "رفع الحزمة", icon: Upload },
  { id: "packages", label: "التحديثات", icon: FileArchive },
  { id: "agent-downloads", label: "Agent Downloads", icon: Download },
  { id: "logs", label: "السجلات", icon: ScrollText },
  { id: "settings", label: "الإعدادات", icon: Settings },
  { id: "users", label: "المستخدمون", icon: Users },
];

export default function Layout({ activePage, setActivePage, onLogout, allowedPages = [], children }) {
  const visibleNav = nav.filter((item) => allowedPages.includes(item.id));

  return (
    <div className="min-h-screen lg:flex" dir="rtl">
      <aside className="border-b border-slate-200 bg-white lg:min-h-screen lg:w-72 lg:border-b-0 lg:border-l">
        <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-600 text-white">
            <Activity size={22} />
          </div>
          <div>
            <div className="text-base font-semibold text-slate-950">ATM Media</div>
            <div className="text-xs text-slate-500">Update Manager</div>
          </div>
        </div>

        <nav className="flex gap-2 overflow-x-auto p-3 lg:block lg:space-y-1">
          {visibleNav.map((item) => {
            const Icon = item.icon;
            const selected = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActivePage(item.id)}
                className={`focus-ring flex min-w-fit items-center gap-2 rounded-lg px-3 py-2 text-sm transition lg:w-full ${
                  selected
                    ? "bg-teal-50 text-teal-800"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
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
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">{children}</div>
      </main>
    </div>
  );
}
