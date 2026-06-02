import { Activity, ArrowLeft, Gauge, Image, LockKeyhole, Monitor, Network, Server, ShieldCheck, Wifi } from "lucide-react";
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
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] w-full max-w-6xl items-center gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="login-visual relative min-h-[560px] overflow-hidden rounded-lg border border-slate-200 bg-white/88 p-6 shadow-sm backdrop-blur">
          <div className="absolute inset-0 login-grid" />
          <div className="relative z-10 flex h-full flex-col justify-between gap-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-lg bg-teal-700 text-white shadow-sm">
                  <Monitor size={25} />
                </div>
                <h1 className="mt-4 text-4xl font-semibold leading-tight text-slate-950">
                  ATM Media Update Manager
                </h1>
              </div>
              <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-semibold text-emerald-700">
                <ShieldCheck size={16} />
                Pull / VPN
              </span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-white/92 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-slate-500">Online</div>
                  <Wifi className="text-emerald-700" size={20} />
                </div>
                <div className="mt-3 text-4xl font-semibold text-emerald-900">24</div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full w-4/5 rounded-full bg-emerald-500" />
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white/92 p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-slate-500">Updates</div>
                  <Activity className="text-amber-700" size={20} />
                </div>
                <div className="mt-3 text-4xl font-semibold text-slate-950">03</div>
                <div className="mt-3 grid grid-cols-3 gap-1">
                  <span className="h-2 rounded-full bg-teal-500" />
                  <span className="h-2 rounded-full bg-amber-400" />
                  <span className="h-2 rounded-full bg-slate-200" />
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-950 p-4 text-white shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="font-semibold">Agent</div>
                <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-200">running</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3">
                  <Server className="mb-2 text-teal-300" size={19} />
                  <div className="text-xs text-slate-400">Server</div>
                  <div className="mt-1 font-semibold">8001</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3">
                  <Image className="mb-2 text-amber-300" size={19} />
                  <div className="text-xs text-slate-400">Media</div>
                  <div className="mt-1 font-semibold">Synced</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-3">
                  <Gauge className="mb-2 text-emerald-300" size={19} />
                  <div className="text-xs text-slate-400">Cash</div>
                  <div className="mt-1 font-semibold">CDM</div>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white/92 px-4 py-3 shadow-sm">
                <div className="text-xs font-semibold text-slate-500">VPN</div>
                <div className="mt-2 flex items-center gap-2 text-teal-800">
                  <Network size={18} />
                  <span className="font-semibold">Active</span>
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white/92 px-4 py-3 shadow-sm">
                <div className="text-xs font-semibold text-slate-500">SHA256</div>
                <div className="mt-2 font-mono text-sm font-semibold text-slate-950">Verified</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white/92 px-4 py-3 shadow-sm">
                <div className="text-xs font-semibold text-slate-500">Audit</div>
                <div className="mt-2 font-semibold text-slate-950">Enabled</div>
              </div>
            </div>
          </div>
        </section>

        <form onSubmit={submit} className="w-full rounded-lg border border-slate-200 bg-white p-6 shadow-sm lg:p-7">
          <div className="mb-7 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-teal-700">Secure Access</div>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">تسجيل الدخول</h2>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-teal-700 text-white shadow-sm">
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
            <span className="rounded-lg bg-slate-50 px-2 py-2">Agent</span>
            <span className="rounded-lg bg-slate-50 px-2 py-2">Media</span>
            <span className="rounded-lg bg-slate-50 px-2 py-2">Cash</span>
          </div>
        </form>
      </div>
    </div>
  );
}
