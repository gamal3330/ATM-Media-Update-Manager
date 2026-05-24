import { ArrowLeft, CheckCircle2, Image, LockKeyhole, Network, Server, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api.login({ username, password });
      localStorage.setItem("atm_media_token", result.access_token);
      onLogin(result.user);
    } catch (err) {
      setError(err.message || "فشل تسجيل الدخول");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen min-h-screen px-4 py-8" dir="rtl">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-6xl items-center gap-8 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="login-visual relative min-h-[420px] overflow-hidden rounded-lg border border-slate-200 bg-white/82 p-6 shadow-sm backdrop-blur">
          <div className="absolute inset-0 login-grid" />
          <div className="relative z-10 flex h-full flex-col justify-between gap-10">
            <div>
              <div className="mb-5 inline-flex items-center gap-2 rounded-lg border border-teal-100 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-800">
                <ShieldCheck size={17} />
                <span>تحديث آمن بنظام Pull عبر VPN</span>
              </div>
              <h1 className="max-w-2xl text-4xl font-semibold leading-tight text-slate-950">
                ATM Media Update Manager
              </h1>
              <p className="mt-4 max-w-xl text-base leading-8 text-slate-600">
                منصة مركزية لإدارة تحديث صور الصرافات، تتابع حالة كل جهاز، تتحقق من سلامة الحزم، وتحفظ نتائج التحديث والنسخ الاحتياطي بدون تنفيذ أوامر على الصراف.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm">
                <Server className="mb-3 text-teal-700" size={24} />
                <div className="text-sm font-semibold text-slate-950">Server</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">رفع الحزم وتعيين الصرافات</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm">
                <Network className="mb-3 text-indigo-700" size={24} />
                <div className="text-sm font-semibold text-slate-950">VPN</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">اتصال داخلي ومراقبة heartbeat</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white/90 p-4 shadow-sm">
                <Image className="mb-3 text-amber-700" size={24} />
                <div className="text-sm font-semibold text-slate-950">Media</div>
                <div className="mt-1 text-xs leading-5 text-slate-500">استبدال الصور مع rollback</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1 text-emerald-800">
                <CheckCircle2 size={14} />
                API Key لكل صراف
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Checksum SHA256</span>
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Audit Logs</span>
            </div>
          </div>
        </section>

        <form onSubmit={submit} className="w-full rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-teal-700 text-white">
              <LockKeyhole size={22} />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-950">تسجيل الدخول</h2>
              <p className="text-sm text-slate-500">لوحة إدارة تحديث صور الصرافات</p>
            </div>
          </div>

          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">اسم المستخدم</span>
            <input
              className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>

          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">كلمة المرور</span>
            <input
              className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>

          {error && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

          <button
            disabled={loading}
            className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span>{loading ? "جار التحقق..." : "دخول"}</span>
            <ArrowLeft size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
