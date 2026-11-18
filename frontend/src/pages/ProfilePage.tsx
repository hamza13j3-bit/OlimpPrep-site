import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fetchHistory, fetchRating, fetchStats } from "../api/client";
import type { HistoryPoint, Lang, RatingOut, StatsOut } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { LANGUAGES, isLanguage, setLanguage } from "../i18n";

interface ChartPoint {
  n: number;
  rating: number;
}

/** Rating after each rated submission, starting from the rating before the first one. */
function toChart(history: HistoryPoint[]): ChartPoint[] {
  if (history.length === 0) return [];
  return [
    { n: 0, rating: Math.round(history[0].old_rating) },
    ...history.map((h, i) => ({ n: i + 1, rating: Math.round(h.new_rating) })),
  ];
}

export default function ProfilePage() {
  const { t, i18n } = useTranslation();
  const { user, updateProfile } = useAuth();
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";
  const [rating, setRating] = useState<RatingOut | null>(null);
  const [stats, setStats] = useState<StatsOut | null>(null);
  const [scope, setScope] = useState<string>(""); // "" = overall
  const [chart, setChart] = useState<ChartPoint[] | null>(null);
  const [error, setError] = useState(false);

  const [name, setName] = useState(user?.name ?? "");
  const [group, setGroup] = useState(user?.school_group ?? "");
  const [lang, setLang] = useState<Lang>(user?.language ?? "kk");
  const [saveState, setSaveState] = useState<"idle" | "saved" | "failed">("idle");

  useEffect(() => {
    fetchRating()
      .then(setRating)
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchStats(uiLang)
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [uiLang]);

  useEffect(() => {
    let cancelled = false;
    setChart(null);
    fetchHistory(scope || undefined)
      .then((h) => {
        if (!cancelled) setChart(toChart(h));
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [scope]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setSaveState("idle");
    try {
      const u = await updateProfile({ name: name.trim(), school_group: group.trim(), language: lang });
      if (isLanguage(u.language)) setLanguage(u.language);
      setSaveState("saved");
    } catch {
      setSaveState("failed");
    }
  }

  if (error) return <p className="text-red-600">{t("common.error")}</p>;
  if (!user || !rating) return <p className="text-slate-500">{t("common.loading")}</p>;

  const avgData = (stats?.tags ?? []).map((x) => ({
    tag: t(`tags.${x.tag}`, { defaultValue: x.tag }),
    avg: Math.round(x.avg_score * 100),
    attempted: x.attempted,
    solved: x.solved,
  }));
  const hasStats = avgData.some((x) => x.attempted > 0);
  const dateFmt = new Intl.DateTimeFormat(uiLang, { day: "numeric", month: "short" });
  const retryItems = stats?.retry ?? [];

  const tagData = rating.tags.map((x) => ({ tag: t(`tags.${x.tag}`, { defaultValue: x.tag }), rating: Math.round(x.rating) }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("profile.title")}</h1>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-1">
          <p className="text-sm text-slate-500">{user.email}</p>
          <p className="text-lg font-semibold">{user.name}</p>
          {user.school_group && <p className="text-sm text-slate-600">{user.school_group}</p>}
          <div className="mt-4">
            <div className="text-sm text-slate-500">{t("profile.rating")}</div>
            <div className="text-4xl font-bold text-brand-700 tabular-nums">{Math.round(rating.rating)}</div>
            <div className="text-sm text-slate-500">{t("profile.attempts", { count: rating.attempts })}</div>
          </div>
        </div>

        <form onSubmit={save} className="card space-y-3 lg:col-span-2">
          <h2 className="font-semibold">{t("profile.edit")}</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block text-sm font-medium">
              {t("auth.name")}
              <input className="input mt-1" required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              {t("auth.group")}
              <input className="input mt-1" maxLength={100} value={group} onChange={(e) => setGroup(e.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              {t("auth.language")}
              <select className="input mt-1" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex items-center gap-3">
            <button className="btn">{t("common.save")}</button>
            {saveState === "saved" && <span className="text-sm text-green-700">{t("common.saved")}</span>}
            {saveState === "failed" && <span className="text-sm text-red-600">{t("common.error")}</span>}
          </div>
        </form>
      </div>

      <section className="card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">{t("profile.history")}</h2>
          <label className="flex items-center gap-2 text-sm">
            {t("profile.chartScope")}
            <select className="rounded border border-slate-300 bg-white px-2 py-1" value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="">{t("profile.overall")}</option>
              {rating.tags.map((x) => (
                <option key={x.tag} value={x.tag}>
                  {t(`tags.${x.tag}`, { defaultValue: x.tag })}
                </option>
              ))}
            </select>
          </label>
        </div>
        {chart === null ? (
          <p className="text-slate-500">{t("common.loading")}</p>
        ) : chart.length === 0 ? (
          <p className="text-slate-500">{t("profile.historyEmpty")}</p>
        ) : (
          <div className="h-72 w-full" role="img" aria-label={t("profile.history")}>
            <ResponsiveContainer>
              <LineChart data={chart} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="n" allowDecimals={false} />
                <YAxis domain={["dataMin - 20", "dataMax + 20"]} allowDecimals={false} width={48} />
                <Tooltip />
                <Line type="monotone" dataKey="rating" stroke="#2559b3" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t("profile.stats.title")}</h2>
        {stats === null ? (
          <p className="text-slate-500">{t("common.loading")}</p>
        ) : !hasStats ? (
          <p className="card text-slate-500">{t("profile.stats.empty")}</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <h3 className="mb-3 font-semibold">{t("profile.stats.avgBar")}</h3>
              <div className="h-72 w-full" role="img" aria-label={t("profile.stats.avgBar")}>
                <ResponsiveContainer>
                  <BarChart data={avgData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="tag" interval={0} tick={{ fontSize: 11 }} />
                    <YAxis domain={[0, 100]} unit="%" width={48} />
                    <Tooltip formatter={(v) => `${String(v)}%`} />
                    <Bar dataKey="avg" name={t("profile.stats.avgScore")} fill="#2f6fdb" isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="card">
              <h3 className="mb-3 font-semibold">{t("profile.stats.avgRadar")}</h3>
              <div className="h-72 w-full" role="img" aria-label={t("profile.stats.avgRadar")}>
                <ResponsiveContainer>
                  <RadarChart data={avgData} outerRadius="70%">
                    <PolarGrid />
                    <PolarAngleAxis dataKey="tag" tick={{ fontSize: 11 }} />
                    <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v) => `${String(v)}%`} />
                    <Radar
                      dataKey="avg"
                      name={t("profile.stats.avgScore")}
                      stroke="#2559b3"
                      fill="#2f6fdb"
                      fillOpacity={0.35}
                      isAnimationActive={false}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        <div className="card">
          <h3 className="font-semibold">{t("profile.stats.retryTitle")}</h3>
          <p className="mb-3 text-xs text-slate-500">{t("profile.stats.retryIntro")}</p>
          {retryItems.length === 0 ? (
            <p className="text-slate-500">{t("profile.stats.retryEmpty")}</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {retryItems.map((item) => (
                <li key={item.problem_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                  <span className="min-w-0">
                    <Link to={`/problems/${item.problem_id}`} className="font-medium">
                      {item.problem_id}. {item.title}
                    </Link>
                    <span className="ml-2 text-slate-500">
                      {t("profile.stats.retryBest", { score: Math.round(item.best_score * 100) })}
                    </span>
                  </span>
                  {item.due ? (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                      {t("profile.stats.retryDue")}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">
                      {t("profile.stats.retryUpcoming")}:{" "}
                      {t("profile.stats.retryOn", { date: dateFmt.format(new Date(item.next_due_at)) })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {tagData.length > 0 && (
        <section className="card">
          <h2 className="mb-3 font-semibold">{t("profile.tagRatings")}</h2>
          <div className="h-72 w-full" role="img" aria-label={t("profile.tagRatings")}>
            <ResponsiveContainer>
              <BarChart data={tagData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="tag" interval={0} tick={{ fontSize: 11 }} />
                <YAxis domain={[800, "dataMax + 50"]} allowDecimals={false} width={48} />
                <Tooltip />
                <Bar dataKey="rating" fill="#2f6fdb" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  );
}
