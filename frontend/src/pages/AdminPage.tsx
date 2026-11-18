import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  ApiError,
  adminAudit,
  adminBlock,
  adminCorrectRating,
  adminPromote,
  adminStats,
  adminUsers,
  fetchTags,
} from "../api/client";
import type { AdminStats, AdminUser, AuditPage, Lang, TagOut } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Pagination from "../components/Pagination";
import { isLanguage } from "../i18n";

const fmt = (iso: string) => new Date(iso).toLocaleString();

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="card !p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function SolvedChart({ title, rows }: { title: string; rows: AdminStats["most_solved"] }) {
  const { t } = useTranslation();
  const data = rows.map((r) => ({ name: `${r.problem_id}. ${r.title}`.slice(0, 28), solved: r.solved }));
  return (
    <div className="card">
      <h3 className="mb-2 font-semibold">{title}</h3>
      <div className="h-72 w-full" role="img" aria-label={title}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="solved" name={t("admin.solvedBy")} fill="#2f6fdb" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RatingForm({ target, tags, onDone }: { target: AdminUser; tags: TagOut[]; onDone: () => void }) {
  const { t } = useTranslation();
  const [scope, setScope] = useState<"global" | "tag" | "duel">("global");
  const [tag, setTag] = useState(tags[0]?.slug ?? "");
  const [rating, setRating] = useState(String(Math.round(target.rating ?? 1200)));
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const valid = reason.trim().length >= 5 && rating.trim() !== "" && Number.isFinite(Number(rating));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    try {
      const r = await adminCorrectRating(target.id, {
        scope,
        tag: scope === "tag" ? tag : undefined,
        rating: Number(rating),
        reason: reason.trim(),
      });
      setMsg({ ok: true, text: t("admin.rating.done", { old: r.old_rating, new: r.new_rating }) });
      setReason("");
      onDone();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError && err.status === 422 ? t("admin.rating.invalid") : t("common.error") });
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="card space-y-3">
      <h3 className="font-semibold">
        {t("admin.rating.title")}: {target.name} ({target.email})
      </h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm font-medium">
          {t("admin.rating.scope")}
          <select className="input mt-1" value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}>
            <option value="global">{t("leaderboard.global")}</option>
            <option value="tag">{t("leaderboard.tag")}</option>
            <option value="duel">{t("leaderboard.duel")}</option>
          </select>
        </label>
        {scope === "tag" && (
          <label className="block text-sm font-medium">
            {t("leaderboard.tag")}
            <select className="input mt-1" value={tag} onChange={(e) => setTag(e.target.value)}>
              {tags.map((x) => (
                <option key={x.slug} value={x.slug}>
                  {t(`tags.${x.slug}`, { defaultValue: x.slug })}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="block text-sm font-medium">
          {t("admin.rating.value")}
          <input className="input mt-1" type="number" min={0} max={5000} value={rating} onChange={(e) => setRating(e.target.value)} />
        </label>
      </div>
      <label className="block text-sm font-medium">
        {t("admin.rating.reason")} *
        <textarea className="input mt-1 w-full" required minLength={5} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="flex items-center gap-3">
        <button className="btn" disabled={!valid}>
          {t("admin.rating.apply")}
        </button>
        {msg && (
          <span role="alert" className={`text-sm ${msg.ok ? "text-green-700" : "text-red-600"}`}>
            {msg.text}
          </span>
        )}
      </div>
    </form>
  );
}

export default function AdminPage() {
  const { t, i18n } = useTranslation();
  const { user: me } = useAuth();
  const lang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [tags, setTags] = useState<TagOut[]>([]);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [usersPage, setUsersPage] = useState(1);
  const [users, setUsers] = useState<{ items: AdminUser[]; total: number; page_size: number } | null>(null);
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [auditPage, setAuditPage] = useState(1);
  const [audit, setAudit] = useState<AuditPage | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    adminStats(lang).then(setStats).catch(() => setError(true));
  }, [lang]);
  useEffect(() => {
    fetchTags().then(setTags).catch(() => undefined);
  }, []);
  useEffect(() => {
    const id = setTimeout(() => {
      setDebounced(query.trim());
      setUsersPage(1);
    }, 300);
    return () => clearTimeout(id);
  }, [query]);

  const loadUsers = useCallback(() => {
    adminUsers(debounced, usersPage).then(setUsers).catch(() => setError(true));
  }, [debounced, usersPage]);
  const loadAudit = useCallback(() => {
    adminAudit(auditPage).then(setAudit).catch(() => setError(true));
  }, [auditPage]);
  useEffect(() => loadUsers(), [loadUsers]);
  useEffect(() => loadAudit(), [loadAudit]);

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      loadUsers();
      loadAudit();
    } catch {
      setError(true);
    }
  }

  if (me?.role !== "admin") return <p className="text-red-600">{t("admin.forbidden")}</p>;
  if (error) return <p className="text-red-600">{t("common.error")}</p>;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">{t("admin.title")}</h1>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t("admin.stats.title")}</h2>
        {stats === null ? (
          <p className="text-slate-500">{t("common.loading")}</p>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label={t("admin.stats.users")} value={stats.users_total} />
              <StatTile label={t("admin.stats.blocked")} value={stats.users_blocked} />
              <StatTile label={t("admin.stats.admins")} value={stats.admins} />
              <StatTile label={t("admin.stats.submissions")} value={stats.submissions_total} />
            </div>
            <div className="card">
              <h3 className="mb-2 font-semibold">{t("admin.stats.perDay")}</h3>
              <div className="h-64 w-full" role="img" aria-label={t("admin.stats.perDay")}>
                <ResponsiveContainer>
                  <LineChart data={stats.submissions_per_day} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" tickFormatter={(d: string) => d.slice(5)} minTickGap={16} />
                    <YAxis allowDecimals={false} width={40} />
                    <Tooltip />
                    <Line type="monotone" dataKey="count" name={t("admin.stats.submissions")} stroke="#2559b3" strokeWidth={2} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <SolvedChart title={t("admin.stats.mostSolved")} rows={stats.most_solved} />
              <SolvedChart title={t("admin.stats.leastSolved")} rows={stats.least_solved} />
            </div>
          </>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">{t("admin.users.title")}</h2>
        <input
          className="input w-full sm:max-w-sm"
          type="search"
          placeholder={t("admin.users.search")}
          aria-label={t("admin.users.search")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {users === null ? (
          <p className="text-slate-500">{t("common.loading")}</p>
        ) : users.items.length === 0 ? (
          <p className="card text-slate-500">{t("admin.users.none")}</p>
        ) : (
          <div className="card overflow-x-auto !p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="px-3 py-2">{t("auth.name")}</th>
                  <th className="px-3 py-2">{t("auth.email")}</th>
                  <th className="px-3 py-2">{t("admin.users.role")}</th>
                  <th className="px-3 py-2">{t("leaderboard.rating")}</th>
                  <th className="px-3 py-2">{t("admin.users.status")}</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {users.items.map((u) => (
                  <tr key={u.id} className="border-t border-slate-100">
                    <td className="px-3 py-2">{u.name}</td>
                    <td className="px-3 py-2">{u.email}</td>
                    <td className="px-3 py-2">{u.role}</td>
                    <td className="px-3 py-2 tabular-nums">{u.rating === null ? "—" : Math.round(u.rating)}</td>
                    <td className="px-3 py-2">
                      {u.is_blocked ? <span className="text-red-600">{t("admin.users.blocked")}</span> : t("admin.users.active")}
                    </td>
                    <td className="space-x-2 whitespace-nowrap px-3 py-2 text-right">
                      {u.id !== me.id && (
                        <button className="btn-secondary !py-0.5 text-xs" onClick={() => void act(() => adminBlock(u.id, !u.is_blocked))}>
                          {u.is_blocked ? t("admin.users.unblock") : t("admin.users.block")}
                        </button>
                      )}
                      {u.role !== "admin" && !u.is_blocked && (
                        <button
                          className="btn-secondary !py-0.5 text-xs"
                          onClick={() => {
                            if (window.confirm(t("admin.users.confirmPromote", { name: u.name }))) void act(() => adminPromote(u.id));
                          }}
                        >
                          {t("admin.users.promote")}
                        </button>
                      )}
                      <button className="btn-secondary !py-0.5 text-xs" onClick={() => setSelected(u)}>
                        {t("admin.users.correct")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={usersPage} pages={users ? Math.max(1, Math.ceil(users.total / users.page_size)) : 1} onChange={setUsersPage} />
        {selected && <RatingForm key={selected.id} target={selected} tags={tags} onDone={() => { loadUsers(); loadAudit(); }} />}
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">{t("admin.audit.title")}</h2>
        {audit === null ? (
          <p className="text-slate-500">{t("common.loading")}</p>
        ) : audit.items.length === 0 ? (
          <p className="card text-slate-500">{t("admin.audit.none")}</p>
        ) : (
          <div className="card overflow-x-auto !p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="px-3 py-2">{t("admin.audit.when")}</th>
                  <th className="px-3 py-2">{t("admin.audit.who")}</th>
                  <th className="px-3 py-2">{t("admin.audit.what")}</th>
                  <th className="px-3 py-2">{t("admin.audit.target")}</th>
                  <th className="px-3 py-2">{t("admin.audit.details")}</th>
                </tr>
              </thead>
              <tbody>
                {audit.items.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 align-top">
                    <td className="whitespace-nowrap px-3 py-2">{fmt(a.created_at)}</td>
                    <td className="px-3 py-2">{a.admin_name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{a.action}</td>
                    <td className="px-3 py-2">
                      {a.target_type} #{a.target_id} {a.target_label}
                    </td>
                    <td className="px-3 py-2 break-words text-xs text-slate-600">
                      {Object.keys(a.details).length ? JSON.stringify(a.details) : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={auditPage} pages={audit ? Math.max(1, Math.ceil(audit.total / audit.page_size)) : 1} onChange={setAuditPage} />
      </section>
    </div>
  );
}
