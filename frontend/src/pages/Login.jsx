import { ArrowLeft, Gauge, Image, LockKeyhole, Monitor, Network } from "lucide-react";
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
    <div className="login-screen flex min-h-screen items-center justify-center px-4 py-8" dir="rtl">
      <div className="w-full max-w-md">
        <div className="mb-5 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-teal-700 text-white shadow-sm">
            <Monitor size={27} />
          </div>
          <h1 className="text-2xl font-semibold text-slate-950">ATM Media Update Manager</h1>
        </div>

        <form onSubmit={submit} className="w-full rounded-lg border border-slate-200 bg-white p-6 shadow-sm lg:p-7">
          <div className="mb-7 flex items-center justify-between gap-3">
            <div>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">تسجيل الدخول</h2>
            </div>
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-slate-50 text-teal-700 ring-1 ring-slate-200">
              <LockKeyhole size={22} />
            </div>
          </div>

          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">اسم المستخدم</span>
            <input
              className="focus-ring min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>

          <label className="mb-4 block">
            <span className="mb-1 block text-sm font-medium text-slate-700">كلمة المرور</span>
            <input
              className="focus-ring min-h-12 w-full rounded-lg border border-slate-300 px-3 py-2"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>

          {error && <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

          <button
            disabled={loading}
            className="focus-ring inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 py-2 font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span>{loading ? "جار التحقق..." : "دخول"}</span>
            <ArrowLeft size={18} />
          </button>

          <div className="mt-6 grid grid-cols-3 gap-2 text-center text-xs font-semibold text-slate-500">
            <span className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-50 px-2 py-2">
              <Network size={14} />
              VPN
            </span>
            <span className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-50 px-2 py-2">
              <Image size={14} />
              Media
            </span>
            <span className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-50 px-2 py-2">
              <Gauge size={14} />
              CDM
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
