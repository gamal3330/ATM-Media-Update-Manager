import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  RefreshCw,
  Save,
  Search,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

const emptyForm = {
  username: "",
  password: "",
  role: "operator",
  is_active: true,
  allowed_pages: ["dashboard"],
};

const roles = [
  { id: "operator", label: "مشغل", tone: "bg-slate-100 text-slate-700" },
  { id: "media_admin", label: "إدارة الوسائط", tone: "bg-sky-50 text-sky-700" },
  { id: "cash_monitoring_viewer", label: "مراقبة النقد", tone: "bg-emerald-50 text-emerald-700" },
  { id: "cash_monitoring_admin", label: "إدارة النقد", tone: "bg-teal-50 text-teal-800" },
  { id: "system_admin", label: "مدير النظام", tone: "bg-violet-50 text-violet-700" },
  { id: "admin", label: "مدير", tone: "bg-violet-50 text-violet-700" },
];

const pageGroups = [
  { title: "العمليات", ids: ["dashboard", "atms", "cash", "notifications"] },
  { title: "التحديثات", ids: ["upload", "packages", "agent-updates", "agent-downloads"] },
  { title: "الإدارة", ids: ["logs", "settings", "users"] },
];

function isAdminRole(role) {
  return role === "admin" || role === "system_admin";
}

function roleMeta(role) {
  return roles.find((item) => item.id === role) || roles[0];
}

function normalizedPages(role, pages, pageOptions) {
  if (isAdminRole(role)) return pageOptions.map((page) => page.id);
  const allowed = (pages || []).filter((page) => page !== "users");
  return allowed.length ? allowed : ["dashboard"];
}

function activePageOptions(role, pageOptions) {
  return pageOptions.filter((page) => isAdminRole(role) || page.id !== "users");
}

function StatusPill({ active }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
        active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
      }`}
    >
      {active ? <UserCheck size={14} /> : <UserX size={14} />}
      <span>{active ? "نشط" : "معطل"}</span>
    </span>
  );
}

function RolePill({ role }) {
  const meta = roleMeta(role);
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${meta.tone}`}>{meta.label}</span>;
}

function StatCard({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-slate-500">{label}</div>
        <Icon size={18} className="text-slate-500" />
      </div>
      <div className="mt-2 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function PageSelector({ role, value, pages, onChange }) {
  const selected = normalizedPages(role, value || [], pages);
  const disabled = isAdminRole(role);
  const pageById = new Map(pages.map((page) => [page.id, page]));

  function toggle(pageId) {
    if (disabled || pageId === "users") return;
    const next = selected.includes(pageId)
      ? selected.filter((item) => item !== pageId)
      : [...selected, pageId];
    onChange(normalizedPages(role, next, pages));
  }

  function selectAll() {
    if (disabled) return;
    onChange(activePageOptions(role, pages).map((page) => page.id));
  }

  function selectMinimum() {
    if (disabled) return;
    onChange(["dashboard"]);
  }

  return (
    <div className="space-y-3">
      {!disabled && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="focus-ring rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            تحديد الكل
          </button>
          <button
            type="button"
            onClick={selectMinimum}
            className="focus-ring rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            لوحة المراقبة فقط
          </button>
        </div>
      )}
      <div className="grid gap-3 lg:grid-cols-3">
        {pageGroups.map((group) => {
          const groupPages = group.ids.map((id) => pageById.get(id)).filter(Boolean);
          if (!groupPages.length) return null;
          return (
            <div key={group.title} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="mb-2 text-xs font-semibold text-slate-500">{group.title}</div>
              <div className="space-y-2">
                {groupPages.map((page) => {
                  const pageDisabled = disabled || page.id === "users";
                  return (
                    <label
                      key={page.id}
                      className={`flex min-h-9 items-center gap-2 rounded-lg border px-2.5 py-2 text-sm ${
                        pageDisabled
                          ? "cursor-not-allowed border-slate-200 bg-white text-slate-500"
                          : "cursor-pointer border-slate-200 bg-white text-slate-700 hover:border-teal-200 hover:bg-teal-50"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(page.id)}
                        disabled={pageDisabled}
                        onChange={() => toggle(page.id)}
                        className="h-4 w-4"
                      />
                      <span className="truncate">{page.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PageSummary({ pages, pageMap }) {
  if (!pages.length) return <span className="text-xs text-slate-500">لا توجد صفحات</span>;
  const visible = pages.slice(0, 4);
  const rest = pages.length - visible.length;
  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map((page) => (
        <span key={page} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
          {pageMap.get(page) || page}
        </span>
      ))}
      {rest > 0 && <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">+{rest}</span>}
    </div>
  );
}

export default function UserManagement({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [pageOptions, setPageOptions] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editForms, setEditForms] = useState({});
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const pageMap = useMemo(() => new Map(pageOptions.map((page) => [page.id, page.label])), [pageOptions]);
  const stats = useMemo(() => {
    const active = users.filter((user) => user.is_active).length;
    const admins = users.filter((user) => isAdminRole(user.role)).length;
    return {
      total: users.length,
      active,
      inactive: users.length - active,
      admins,
    };
  }, [users]);
  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return users.filter((user) => {
      const edit = editForms[user.id] || {};
      const pages = normalizedPages(edit.role || user.role, edit.allowed_pages || user.allowed_pages || [], pageOptions);
      const haystack = [
        user.username,
        user.role,
        roleMeta(user.role).label,
        ...pages.map((page) => pageMap.get(page) || page),
      ].join(" ").toLowerCase();
      const matchesSearch = !query || haystack.includes(query);
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && user.is_active) ||
        (statusFilter === "inactive" && !user.is_active);
      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [editForms, pageMap, pageOptions, roleFilter, search, statusFilter, users]);

  function buildEditForms(nextUsers) {
    const forms = {};
    nextUsers.forEach((user) => {
      forms[user.id] = {
        username: user.username,
        password: "",
        role: user.role,
        is_active: user.is_active,
        allowed_pages: user.allowed_pages || [],
      };
    });
    setEditForms(forms);
  }

  async function loadUsers() {
    setLoading(true);
    setError("");
    try {
      const [pages, userData] = await Promise.all([api.listUserPages(), api.listUsers()]);
      setPageOptions(pages);
      setUsers(userData);
      buildEditForms(userData);
    } catch (err) {
      setError(err.message || "تعذر تحميل المستخدمين");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  function updateForm(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "role") {
        next.allowed_pages = normalizedPages(value, current.allowed_pages, pageOptions);
      }
      return next;
    });
  }

  function updateEditForm(userId, key, value) {
    setEditForms((current) => {
      const existing = current[userId] || {};
      const next = { ...existing, [key]: value };
      if (key === "role") {
        next.allowed_pages = normalizedPages(value, existing.allowed_pages || [], pageOptions);
      }
      return { ...current, [userId]: next };
    });
  }

  async function createUser(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        ...form,
        username: form.username.trim(),
        allowed_pages: normalizedPages(form.role, form.allowed_pages, pageOptions),
      };
      await api.createUser(payload);
      setForm(emptyForm);
      setMessage("تم إنشاء المستخدم.");
      await loadUsers();
    } catch (err) {
      setError(err.message || "تعذر إنشاء المستخدم");
    } finally {
      setSaving(false);
    }
  }

  async function saveUser(user) {
    const edit = editForms[user.id];
    if (!edit) return;

    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        username: edit.username.trim(),
        role: edit.role,
        is_active: edit.is_active,
        allowed_pages: normalizedPages(edit.role, edit.allowed_pages || [], pageOptions),
      };
      if (edit.password) payload.password = edit.password;
      await api.updateUser(user.id, payload);
      setMessage(`تم حفظ المستخدم ${payload.username}.`);
      await loadUsers();
    } catch (err) {
      setError(err.message || "تعذر حفظ المستخدم");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateUser(user) {
    const confirmed = window.confirm(`هل تريد تعطيل المستخدم ${user.username}؟`);
    if (!confirmed) return;

    setSaving(true);
    setMessage("");
    setError("");
    try {
      await api.deleteUser(user.id);
      setMessage(`تم تعطيل المستخدم ${user.username}.`);
      await loadUsers();
    } catch (err) {
      setError(err.message || "تعذر تعطيل المستخدم");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
          <Users size={26} />
          <span>إدارة المستخدمين</span>
        </h1>
        <button
          type="button"
          onClick={loadUsers}
          disabled={loading}
          className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          title="تحديث المستخدمين"
        >
          <RefreshCw size={16} />
          <span>{loading ? "جار التحديث" : "تحديث"}</span>
        </button>
      </div>

      {message && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          <CheckCircle2 className="mt-0.5 shrink-0" size={17} />
          <span>{message}</span>
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 shrink-0" size={17} />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="المستخدمون" value={stats.total} />
        <StatCard icon={UserCheck} label="نشط" value={stats.active} />
        <StatCard icon={UserX} label="معطل" value={stats.inactive} />
        <StatCard icon={ShieldCheck} label="مدراء" value={stats.admins} />
      </div>

      <form onSubmit={createUser} className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold text-slate-950">
            <UserPlus size={18} />
            <span>مستخدم جديد</span>
          </div>
          <StatusPill active={form.is_active} />
        </div>
        <div className="space-y-4 p-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_220px_120px]">
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">اسم المستخدم</span>
              <input
                value={form.username}
                onChange={(event) => updateForm("username", event.target.value)}
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                required
                minLength={2}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">كلمة المرور</span>
              <input
                value={form.password}
                onChange={(event) => updateForm("password", event.target.value)}
                className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                type="password"
                required
                minLength={8}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">الدور</span>
              <select
                value={form.role}
                onChange={(event) => updateForm("role", event.target.value)}
                className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
              >
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex min-h-10 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm md:mt-6">
              <span className="font-medium text-slate-700">نشط</span>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => updateForm("is_active", event.target.checked)}
                className="h-4 w-4"
              />
            </label>
          </div>

          <details className="rounded-lg border border-slate-200 bg-slate-50 p-3" open>
            <summary className="cursor-pointer text-sm font-semibold text-slate-700">الصلاحيات</summary>
            <div className="mt-3">
              <PageSelector
                role={form.role}
                value={form.allowed_pages}
                pages={pageOptions}
                onChange={(pages) => updateForm("allowed_pages", pages)}
              />
            </div>
          </details>
        </div>
        <div className="flex justify-end border-t border-slate-100 px-4 py-3">
          <button
            disabled={saving}
            className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
            title="إنشاء مستخدم"
          >
            <UserPlus size={17} />
            <span>{saving ? "جار الحفظ..." : "إنشاء مستخدم"}</span>
          </button>
        </div>
      </form>

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold text-slate-950">
            <SlidersHorizontal size={18} />
            <span>المستخدمون</span>
          </div>
          <div className="flex flex-1 flex-wrap justify-end gap-2">
            <label className="relative min-w-[220px] flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="focus-ring w-full rounded-lg border border-slate-300 py-2 pl-3 pr-9 text-sm"
                placeholder="بحث"
              />
            </label>
            <select
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value)}
              className="focus-ring rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="all">كل الأدوار</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.label}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="focus-ring rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="all">كل الحالات</option>
              <option value="active">نشط</option>
              <option value="inactive">معطل</option>
            </select>
          </div>
        </div>

        <div className="divide-y divide-slate-100">
          {filteredUsers.map((user) => {
            const edit = editForms[user.id] || {};
            const isCurrentUser = user.id === currentUser?.id;
            const pages = normalizedPages(edit.role || user.role, edit.allowed_pages || [], pageOptions);

            return (
              <div key={user.id} className="px-4 py-4">
                <div className="grid gap-3 xl:grid-cols-[minmax(220px,1.1fr)_190px_minmax(220px,1fr)_160px]">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Shield size={17} className="text-slate-500" />
                      <span className="font-semibold text-slate-950">{user.username}</span>
                      {isCurrentUser && <span className="rounded-full bg-teal-50 px-2 py-0.5 text-xs text-teal-700">أنت</span>}
                      <StatusPill active={Boolean(edit.is_active)} />
                    </div>
                    <input
                      value={edit.username || ""}
                      onChange={(event) => updateEditForm(user.id, "username", event.target.value)}
                      className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    />
                  </div>

                  <label className="block">
                    <span className="mb-2 block text-xs font-semibold text-slate-500">الدور</span>
                    <select
                      value={edit.role || "operator"}
                      onChange={(event) => updateEditForm(user.id, "role", event.target.value)}
                      disabled={isCurrentUser}
                      className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:bg-slate-50"
                    >
                      {roles.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.label}
                        </option>
                      ))}
                    </select>
                    <div className="mt-2">
                      <RolePill role={edit.role || user.role} />
                    </div>
                  </label>

                  <label className="block">
                    <span className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
                      <KeyRound size={14} />
                      <span>كلمة مرور جديدة</span>
                    </span>
                    <input
                      value={edit.password || ""}
                      onChange={(event) => updateEditForm(user.id, "password", event.target.value)}
                      className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                      type="password"
                      placeholder="اتركها فارغة"
                    />
                    <div className="mt-2">
                      <PageSummary pages={pages} pageMap={pageMap} />
                    </div>
                  </label>

                  <div className="flex flex-col justify-between gap-3">
                    <label className="flex min-h-10 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                      <span className="font-medium text-slate-700">نشط</span>
                      <input
                        type="checkbox"
                        checked={Boolean(edit.is_active)}
                        disabled={isCurrentUser}
                        onChange={(event) => updateEditForm(user.id, "is_active", event.target.checked)}
                        className="h-4 w-4"
                      />
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => saveUser(user)}
                        disabled={saving}
                        className="focus-ring inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-teal-700 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                        title="حفظ المستخدم"
                      >
                        <Save size={16} />
                        <span>حفظ</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => deactivateUser(user)}
                        disabled={saving || isCurrentUser || !user.is_active}
                        className="focus-ring inline-flex min-h-10 items-center justify-center rounded-lg border border-rose-200 px-3 py-2 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                        title="تعطيل المستخدم"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>

                <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-700">الصلاحيات</summary>
                  <div className="mt-3">
                    <PageSelector
                      role={edit.role || user.role}
                      value={pages}
                      pages={pageOptions}
                      onChange={(nextPages) => updateEditForm(user.id, "allowed_pages", nextPages)}
                    />
                  </div>
                </details>
              </div>
            );
          })}
          {!loading && filteredUsers.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-slate-500">لا توجد نتائج</div>
          )}
        </div>
      </div>
    </section>
  );
}
