import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, duelResult } from "../api/client";
import type { DuelResult, Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { isLanguage } from "../i18n";

const sign = (n: number | null) => (n === null ? "—" : `${n > 0 ? "+" : ""}${n}`);

export default function DuelResultPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const params = useParams();
  const id = Number(params.id);
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";
  const [data, setData] = useState<DuelResult | null>(null);
  const [error, setError] = useState<"missing" | "failed" | null>(null);

  useEffect(() => {
    if (!Number.isInteger(id)) {
      setError("missing");
      return;
    }
    let cancelled = false;
    duelResult(id, uiLang)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError && (e.status === 404 || e.status === 409) ? "missing" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [id, uiLang]);

  if (error) return <p className={error === "missing" ? "" : "text-red-600"}>{error === "missing" ? t("common.notFound") : t("common.error")}</p>;
  if (!data) return <p className="text-slate-500">{t("common.loading")}</p>;

  const me = data.players.find((p) => p.user_id === user?.id);
  const outcome = data.draw ? "draw" : data.winner_id === user?.id ? "win" : "loss";
  const banner = data.draw ? "bg-slate-100 text-slate-800" : outcome === "win" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800";
  const titles = new Map(data.problems.map((p) => [p.problem_id, p]));

  return (
    <div className="space-y-6">
      <div className={`card text-center ${banner}`}>
        <div className="text-3xl font-bold">{me ? t(`duel.outcome.${outcome}`) : t("duel.finished")}</div>
        <div className="text-sm">{t(`duel.reason.${data.reason}`, { defaultValue: "" })}</div>
        {me && me.rating_change !== null && (
          <div className="mt-1 text-lg font-semibold tabular-nums">
            {t("duel.rating")}: {Math.round(me.rating_before)} → {Math.round(me.rating_after ?? me.rating_before)} ({sign(me.rating_change)})
          </div>
        )}
      </div>

      <div className="card overflow-x-auto !p-0">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">{t("leaderboard.name")}</th>
              <th className="px-3 py-2 text-right">{t("duel.solvedCount")}</th>
              <th className="px-3 py-2 text-right">{t("duel.totalScore")}</th>
              <th className="px-3 py-2 text-right">{t("duel.penalty")}</th>
              <th className="px-3 py-2 text-right">{t("duel.failedSubmissions")}</th>
              <th className="px-3 py-2 text-right">{t("duel.ratingChange")}</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p) => (
              <tr key={p.user_id} className={`border-t border-slate-100 ${p.user_id === user?.id ? "bg-brand-50 font-semibold" : ""}`}>
                <td className="px-3 py-2">
                  {p.name} {p.user_id === data.winner_id && "🏆"}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {p.solved}/{data.problems.length}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{Math.round(p.total_score * 100)}%</td>
                <td className="px-3 py-2 text-right tabular-nums">{p.penalty_minutes}</td>
                <td className="px-3 py-2 text-right tabular-nums">{p.failed_submissions}</td>
                <td className="px-3 py-2 text-right tabular-nums">{sign(p.rating_change)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {data.players.map((p) => (
          <div key={p.user_id} className="card">
            <h3 className="mb-2 font-semibold">{p.name}</h3>
            <ul className="space-y-1 text-sm">
              {p.problems.map((pp, i) => (
                <li key={pp.problem_id} className="flex flex-wrap justify-between gap-2">
                  <span>
                    {String.fromCharCode(65 + i)}. {titles.get(pp.problem_id)?.title}
                  </span>
                  <span className="tabular-nums text-slate-600">
                    {pp.solved
                      ? `✓ ${pp.solved_minutes} ${t("duel.min")}`
                      : `${Math.round(pp.best_score * 100)}%`}
                    {pp.failed_submissions > 0 && ` · ${t("duel.failedShort", { count: pp.failed_submissions })}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <p className="text-center">
        <Link to="/duel" className="btn no-underline text-white">
          {t("duel.again")}
        </Link>
      </p>
    </div>
  );
}
