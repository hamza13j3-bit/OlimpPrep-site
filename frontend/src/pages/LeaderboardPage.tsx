import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchLeaderboard, fetchTags } from "../api/client";
import type { LeaderPage, TagOut } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Pagination from "../components/Pagination";

type Kind = "global" | "tag" | "duel";

export default function LeaderboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [kind, setKind] = useState<Kind>("global");
  const [tags, setTags] = useState<TagOut[]>([]);
  const [tag, setTag] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LeaderPage | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchTags()
      .then((list) => {
        setTags(list);
        setTag((cur) => cur || list[0]?.slug || "");
      })
      .catch(() => undefined);
  }, []);

  const load = useCallback(() => {
    if (kind === "tag" && !tag) return () => undefined;
    let cancelled = false;
    setError(false);
    fetchLeaderboard(kind === "tag" ? { tag } : kind, page)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, tag, page]);

  useEffect(() => load(), [load, user?.id]);

  function pick(next: Kind) {
    setKind(next);
    setPage(1);
    setData(null);
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const tabClass = (active: boolean) =>
    `rounded px-3 py-1.5 text-sm font-medium ${active ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("leaderboard.title")}</h1>

      <div className="flex flex-wrap items-center gap-2">
        {(["global", "tag", "duel"] as const).map((k) => (
          <button key={k} className={tabClass(kind === k)} onClick={() => pick(k)}>
            {t(`leaderboard.${k}`)}
          </button>
        ))}
        {kind === "tag" && (
          <select
            aria-label={t("leaderboard.tag")}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
            value={tag}
            onChange={(e) => {
              setTag(e.target.value);
              setPage(1);
              setData(null);
            }}
          >
            {tags.map((x) => (
              <option key={x.slug} value={x.slug}>
                {t(`tags.${x.slug}`, { defaultValue: x.slug })}
              </option>
            ))}
          </select>
        )}
        {user && data?.me && (
          <button className="btn-secondary ml-auto" onClick={() => setPage(data.me!.page)}>
            {t("leaderboard.myPosition")}: #{data.me.rank}
          </button>
        )}
      </div>
      {user && data && !data.me && <p className="text-sm text-slate-500">{t("leaderboard.notRanked")}</p>}

      {error ? (
        <p className="text-red-600">{t("common.error")}</p>
      ) : data === null ? (
        <p className="text-slate-500">{t("common.loading")}</p>
      ) : data.items.length === 0 ? (
        <p className="card text-slate-500">{t("leaderboard.empty")}</p>
      ) : (
        <div className="card overflow-x-auto !p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="w-16 px-3 py-2">{t("leaderboard.rank")}</th>
                <th className="px-3 py-2">{t("leaderboard.name")}</th>
                <th className="px-3 py-2 text-right">{t("leaderboard.rating")}</th>
                <th className="px-3 py-2 text-right">{t("leaderboard.solved")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr
                  key={row.user_id}
                  aria-current={row.is_me ? "true" : undefined}
                  className={`border-t border-slate-100 ${row.is_me ? "bg-brand-50 font-semibold" : ""}`}
                >
                  <td className="px-3 py-2 tabular-nums">{row.rank}</td>
                  <td className="px-3 py-2">
                    {row.name}
                    {row.is_me && <span className="ml-2 text-xs text-brand-700">({t("leaderboard.you")})</span>}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.rating}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{row.solved}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pages={pages} onChange={setPage} />
    </div>
  );
}
