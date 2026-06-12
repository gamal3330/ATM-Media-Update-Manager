import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Pencil,
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
  XCircle,
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
  { title: "الصرافات", ids: ["atms", "atms-manage"] },
  { title: "العمليات", ids: ["dashboard", "cash", "notifications"] },
  { title: "التحديثات", ids: ["upload", "packages", "agent-updates", "agent-downloads"] },
  { title: "الإدارة", ids: ["logs", "journal", "settings", "users"] },
];

const pageSizeOptions = [10, 25, 50, 100];

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
    const next = selected.includes(pageId) ? selected.filter((item) => item !== pageId) : [...selected, pageId];
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
      {disabled && (
        <div className="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2 text-sm text-violet-700">
          هذا الدور يحصل على كل الصلاحيات تلقائياً.
        </div>
      )}
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
      <div className="grid gap-3 sm:grid-cols-2">
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
  if (!pages.length) return <span className="text-xs text-slate-500">لا توجد صلاحيات</span>;
  const visible = pages.slice(0, 3);
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

function Drawer({ title, subtitle, onClose, children }) {
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/40"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-3xl flex-col bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold text-slate-950">{title}</h2>
            {subtitle && <div className="mt-1 text-sm text-slate-500">{subtitle}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="focus-ring rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
            title="إغلاق"
          >
            <XCircle size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function UserFields({ value, onChange, pageOptions, mode, isCurrentUser }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-slate-700">اسم المستخدم</span>
          <input
            value={value.username || ""}
            onChange={(event) => onChange("username", event.target.value)}
            className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
            required
            minLength={2}
          />
        </label>
        <label className="block">
          <span className="mb-1 flex items-center gap-1.5 text-sm font-medium text-slate-700">
            <KeyRound size={15} />
            <span>{mode === "create" ? "كلمة المرور" : "كلمة مرور جديدة"}</span>
          </span>
          <input
            value={value.password || ""}
            onChange={(event) => onChange("password", event.target.value)}
            className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
            type="password"
            required={mode === "create"}
            minLength={mode === "create" || value.password ? 8 : undefined}
            placeholder={mode === "create" ? "" : "اتركها فارغة بدون تغيير"}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-slate-700">الدور</span>
          <select
            value={value.role || "operator"}
            onChange={(event) => onChange("role", event.target.value)}
            disabled={isCurrentUser}
            className="focus-ring w-full rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-50"
          >
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-h-11 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm md:mt-6">
          <span className="font-medium text-slate-700">نشط</span>
          <input
            type="checkbox"
            checked={Boolean(value.is_active)}
            disabled={isCurrentUser}
            onChange={(event) => onChange("is_active", event.target.checked)}
            className="h-4 w-4"
          />
        </label>
      </div>
      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 font-semibold text-slate-950">
          الصلاحيات
        </div>
        <div className="p-4">
          <PageSelector
            role={value.role}
            value={value.allowed_pages}
            pages={pageOptions}
            onChange={(pages) => onChange("allowed_pages", pages)}
          />
        </div>
      </section>
    </div>
  );
}

export default function UserManagement({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [pageOptions, setPageOptions] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editForms, setEditForms] = useState({});
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const pageMap = useMemo(() => new Map(pageOptions.map((item) => [item.id, item.label])), [pageOptions]);
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
    return [...users]
      .filter((user) => {
        const pages = normalizedPages(user.role, user.allowed_pages || [], pageOptions);
        const haystack = [
          user.username,
          user.role,
          roleMeta(user.role).label,
          ...pages.map((item) => pageMap.get(item) || item),
        ]
          .join(" ")
          .toLowerCase();
        const matchesSearch = !query || haystack.includes(query);
        const matchesRole = roleFilter === "all" || user.role === roleFilter;
        const matchesStatus =
          statusFilter === "all" ||
          (statusFilter === "active" && user.is_active) ||
          (statusFilter === "inactive" && !user.is_active);
        return matchesSearch && matchesRole && matchesStatus;
      })
      .sort((first, second) => String(first.username).localeCompare(String(second.username), "ar", { sensitivity: "base" }));
  }, [pageMap, pageOptions, roleFilter, search, statusFilter, users]);

  const pageCount = Math.max(1, Math.ceil(filteredUsers.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = filteredUsers.length ? (currentPage - 1) * pageSize : 0;
  const endIndex = Math.min(startIndex + pageSize, filteredUsers.length);
  const visibleUsers = filteredUsers.slice(startIndex, endIndex);
  const selectedUser = users.find((user) => user.id === selectedUserId) || null;
  const selectedEdit = selectedUser ? editForms[selectedUser.id] || {} : {};

  useEffect(() => {
    setPage(1);
  }, [pageSize, roleFilter, search, statusFilter]);

  useEffect(() => {
    loadUsers();
  }, []);

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
      setShowCreateForm(false);
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
      setSelectedUserId(null);
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
      if (selectedUserId === user.id) setSelectedUserId(null);
      setMessage(`تم تعطيل المستخدم ${user.username}.`);
      await loadUsers();
    } catch (err) {
      setError(err.message || "تعذر تعطيل المستخدم");
    } finally {
      setSaving(false);
    }
  }

  function resetFilters() {
    setSearch("");
    setRoleFilter("all");
    setStatusFilter("all");
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
          <Users size={26} />
          <span>إدارة المستخدمين</span>
        </h1>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadUsers}
            disabled={loading}
            className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            title="تحديث المستخدمين"
          >
            <RefreshCw size={16} />
            <span>{loading ? "جاري التحديث" : "تحديث"}</span>
          </button>
          <button
            type="button"
            onClick={() => setShowCreateForm(true)}
            className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800"
            title="إضافة مستخدم"
          >
            <UserPlus size={17} />
            <span>إضافة مستخدم</span>
          </button>
        </div>
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

      <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="flex items-center gap-2 font-semibold text-slate-950">
            <SlidersHorizontal size={18} />
            <span>قائمة المستخدمين</span>
          </div>
          <span className="text-sm text-slate-500">
            المعروض {filteredUsers.length ? startIndex + 1 : 0}-{endIndex} من {filteredUsers.length}
          </span>
        </div>

        <div className="grid gap-3 border-b border-slate-100 px-4 py-3 xl:grid-cols-[minmax(260px,1fr)_180px_160px_150px_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="focus-ring min-h-10 w-full rounded-lg border border-slate-300 py-2 pl-3 pr-9 text-sm"
              placeholder="بحث باسم المستخدم أو الدور أو الصلاحية"
            />
          </label>
          <select
            value={roleFilter}
            onChange={(event) => setRoleFilter(event.target.value)}
            className="focus-ring min-h-10 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
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
            className="focus-ring min-h-10 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="all">كل الحالات</option>
            <option value="active">نشط</option>
            <option value="inactive">معطل</option>
          </select>
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
            className="focus-ring min-h-10 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size} لكل صفحة
              </option>
            ))}
          </select>
          {(search || roleFilter !== "all" || statusFilter !== "all") && (
            <button
              type="button"
              onClick={resetFilters}
              className="focus-ring inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50"
              title="مسح الفلاتر"
            >
              <XCircle size={16} />
              <span>مسح</span>
            </button>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] table-fixed text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-semibold text-slate-500">
              <tr>
                <th className="w-[28%] px-4 py-3 text-right">المستخدم</th>
                <th className="w-[17%] px-4 py-3 text-right">الدور</th>
                <th className="w-[13%] px-4 py-3 text-right">الحالة</th>
                <th className="w-[27%] px-4 py-3 text-right">الصلاحيات</th>
                <th className="w-[15%] px-4 py-3 text-right">إجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visibleUsers.map((user) => {
                const isCurrentUser = user.id === currentUser?.id;
                const pages = normalizedPages(user.role, user.allowed_pages || [], pageOptions);
                return (
                  <tr key={user.id} className="align-middle hover:bg-slate-50/70">
                    <td className="px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <Shield size={17} className="shrink-0 text-slate-500" />
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-slate-950">{user.username}</div>
                          {isCurrentUser && <div className="text-xs text-teal-700">أنت</div>}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <RolePill role={user.role} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill active={user.is_active} />
                    </td>
                    <td className="px-4 py-3">
                      <PageSummary pages={pages} pageMap={pageMap} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedUserId(user.id)}
                          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-300 text-slate-700 hover:bg-white"
                          title="تعديل المستخدم"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          type="button"
                          onClick={() => deactivateUser(user)}
                          disabled={saving || isCurrentUser || !user.is_active}
                          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                          title="تعطيل المستخدم"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!loading && visibleUsers.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-slate-500">لا توجد نتائج مطابقة</div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-sm">
          <div className="text-slate-500">
            صفحة {currentPage} من {pageCount}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={currentPage <= 1}
              className="focus-ring min-h-9 rounded-lg border border-slate-300 px-3 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              السابق
            </button>
            <button
              type="button"
              onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
              disabled={currentPage >= pageCount}
              className="focus-ring min-h-9 rounded-lg border border-slate-300 px-3 text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              التالي
            </button>
          </div>
        </div>
      </div>

      {showCreateForm && (
        <Drawer title="إضافة مستخدم" subtitle="أنشئ المستخدم وحدد صلاحياته من نفس النافذة." onClose={() => setShowCreateForm(false)}>
          <form onSubmit={createUser} className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <UserFields value={form} onChange={updateForm} pageOptions={pageOptions} mode="create" />
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="focus-ring min-h-10 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                إلغاء
              </button>
              <button
                disabled={saving}
                className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
              >
                <UserPlus size={17} />
                <span>{saving ? "جاري الحفظ..." : "إنشاء مستخدم"}</span>
              </button>
            </div>
          </form>
        </Drawer>
      )}

      {selectedUser && (
        <Drawer
          title={`تعديل ${selectedUser.username}`}
          subtitle="عدّل بيانات المستخدم أو صلاحياته، ثم احفظ التغيير."
          onClose={() => setSelectedUserId(null)}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              saveUser(selectedUser);
            }}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <UserFields
                value={selectedEdit}
                onChange={(key, value) => updateEditForm(selectedUser.id, key, value)}
                pageOptions={pageOptions}
                mode="edit"
                isCurrentUser={selectedUser.id === currentUser?.id}
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-5 py-4">
              <button
                type="button"
                onClick={() => deactivateUser(selectedUser)}
                disabled={saving || selectedUser.id === currentUser?.id || !selectedUser.is_active}
                className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg border border-rose-200 px-4 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50"
              >
                <Trash2 size={16} />
                <span>تعطيل</span>
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedUserId(null)}
                  className="focus-ring min-h-10 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                >
                  إلغاء
                </button>
                <button
                  disabled={saving}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  <Save size={17} />
                  <span>{saving ? "جاري الحفظ..." : "حفظ"}</span>
                </button>
              </div>
            </div>
          </form>
        </Drawer>
      )}
    </section>
  );
}
