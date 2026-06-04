export default function StatCard({ label, value, tone = "neutral" }) {
  const tones = {
    neutral: "border-slate-200 bg-white text-slate-900",
    good: "border-emerald-200 bg-emerald-50 text-emerald-900",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    bad: "border-rose-200 bg-rose-50 text-rose-900",
    info: "border-teal-200 bg-teal-50 text-teal-900",
  };

  return (
    <div className={`rounded-lg border p-4 shadow-sm ${tones[tone]}`}>
      <div className="text-sm text-slate-600">{label}</div>
      <div className="mt-2 text-2xl font-semibold sm:text-3xl">{value}</div>
    </div>
  );
}

