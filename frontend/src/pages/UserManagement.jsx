import { AlertCircle, CheckCircle2, RefreshCw, Save, Shield, Trash2, UserPlus, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";

const emptyForm = {
  username: "",
  password: "",
  role: "operator",
  is_active: true,
  allowed_pages: ["dashboard"],
};

function normalizedPages(role, pages, pageOptions) {
  if (role === "admin") return pageOptions.map((page) => page.id);
  const allowed = pages.filter((page) => page !== "users");
  return allowed.length ? allowed : ["dashboard"];
}

function PageSelector({ role, value, pages, onChange }) {
  const selected = normalizedPages(role, value || [], pages);
  const disabled = role === "admin";

  function toggle(pageId) {
    if (disabled) return;
    const next = selected.includes(pageId)
      ? selected.filter((item) => item !== pageId)
      : [...selected, pageId];
    onChange(normalizedPages(role, next, pages));
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {pages.map((page) => (
        <label
          key={page.id}
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
            disabled || page.id === "users"
              ? "cursor-not-allowed border-slate-200 bg-slate-50 text-slate-500"
              : "cursor-pointer border-slate-200 bg-white hover:bg-slate-50"
          }`}
        >
          <input
            type="checkbox"
            checked={selected.includes(page.id)}
            disabled={disabled || page.id === "users"}
            onChange={() => toggle(page.id)}
            className="h-4 w-4"
          />
          <span>{page.label}</span>
        </label>
      ))}
    </div>
  );
}

export default function UserManagement({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [pageOptions, setPageOptions] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editForms, setEditForms] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const pageMap = useMemo(() => new Map(pageOptions.map((page) => [page.id, page.label])), [pageOptions]);

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
    <section>
      <div className="mb-5">
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950">
          <Users size={26} />
          <span>إدارة المستخدمين</span>
        </h1>
        <p className="text-sm text-slate-500">إنشاء المستخدمين وتحديد الصفحات التي تظهر لكل مستخدم</p>
      </div>

      {message && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          <CheckCircle2 className="mt-0.5 shrink-0" size={17} />
          <span>{message}</span>
        </div>
      )}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          <AlertCircle className="mt-0.5 shrink-0" size={17} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={createUser} className="mb-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-4 flex items-center gap-2 font-semibold text-slate-950">
          <UserPlus size={18} />
          <span>مستخدم جديد</span>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
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
              className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="operator">Operator</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <label className="flex items-center gap-2 pt-7 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => updateForm("is_active", event.target.checked)}
              className="h-4 w-4"
            />
            <span>نشط</span>
          </label>
        </div>
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-slate-700">الصفحات المسموحة</div>
          <PageSelector
            role={form.role}
            value={form.allowed_pages}
            pages={pageOptions}
            onChange={(pages) => updateForm("allowed_pages", pages)}
          />
        </div>
        <button
          disabled={saving}
          className="focus-ring mt-4 inline-flex items-center gap-2 rounded-lg bg-teal-700 px-4 py-2 text-white hover:bg-teal-800 disabled:opacity-60"
          title="إنشاء مستخدم"
        >
          <UserPlus size={17} />
          <span>{saving ? "جار الحفظ..." : "إنشاء مستخدم"}</span>
        </button>
      </form>

      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm text-slate-500">{users.length} مستخدم</div>
        <button
          onClick={loadUsers}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          title="تحديث المستخدمين"
        >
          <RefreshCw size={16} />
          <span>{loading ? "جار التحديث" : "تحديث"}</span>
        </button>
      </div>

      <div className="space-y-4">
        {users.map((user) => {
          const edit = editForms[user.id] || {};
          const isCurrentUser = user.id === currentUser?.id;
          const pages = normalizedPages(edit.role || user.role, edit.allowed_pages || [], pageOptions);

          return (
            <div key={user.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-950">
                    <Shield size={17} />
                    <span>{user.username}</span>
                    {isCurrentUser && <span className="rounded-full bg-teal-50 px-2 py-0.5 text-xs text-teal-700">أنت</span>}
                  </div>
                  <div className="mt-1 text-sm text-slate-500">
                    {user.role} · {user.is_active ? "نشط" : "معطل"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => saveUser(user)}
                    disabled={saving}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg bg-teal-700 px-3 py-2 text-sm text-white hover:bg-teal-800 disabled:opacity-60"
                    title="حفظ المستخدم"
                  >
                    <Save size={16} />
                    <span>حفظ</span>
                  </button>
                  <button
                    onClick={() => deactivateUser(user)}
                    disabled={saving || isCurrentUser || !user.is_active}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-rose-200 px-3 py-2 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                    title="تعطيل المستخدم"
                  >
                    <Trash2 size={16} />
                    <span>تعطيل</span>
                  </button>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-4">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">اسم المستخدم</span>
                  <input
                    value={edit.username || ""}
                    onChange={(event) => updateEditForm(user.id, "username", event.target.value)}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">كلمة مرور جديدة</span>
                  <input
                    value={edit.password || ""}
                    onChange={(event) => updateEditForm(user.id, "password", event.target.value)}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2"
                    type="password"
                    placeholder="اتركها فارغة"
                  />
                </label>
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-slate-700">الدور</span>
                  <select
                    value={edit.role || "operator"}
                    onChange={(event) => updateEditForm(user.id, "role", event.target.value)}
                    disabled={isCurrentUser}
                    className="focus-ring w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50"
                  >
                    <option value="operator">Operator</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 pt-7 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={Boolean(edit.is_active)}
                    disabled={isCurrentUser}
                    onChange={(event) => updateEditForm(user.id, "is_active", event.target.checked)}
                    className="h-4 w-4"
                  />
                  <span>نشط</span>
                </label>
              </div>

              <div className="mt-4">
                <div className="mb-2 text-sm font-medium text-slate-700">الصفحات المسموحة</div>
                <PageSelector
                  role={edit.role || user.role}
                  value={pages}
                  pages={pageOptions}
                  onChange={(nextPages) => updateEditForm(user.id, "allowed_pages", nextPages)}
                />
                <div className="mt-2 text-xs text-slate-500">
                  {pages.map((page) => pageMap.get(page) || page).join(" · ")}
                </div>
              </div>
            </div>
          );
        })}
        {!loading && users.length === 0 && (
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500 shadow-sm">
            لا توجد مستخدمين
          </div>
        )}
      </div>
    </section>
  );
}
