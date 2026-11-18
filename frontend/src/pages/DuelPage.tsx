import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, duelHistory, duelJoin, duelLeave, duelRating } from "../api/client";
import type { DuelHistoryItem, DuelRatingView, Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import DuelMatch from "../duel/DuelMatch";
import { useDuel } from "../duel/useDuel";
import { isLanguage } from "../i18n";

/** Seconds spent waiting. The server only pushes the state every ~5 s, so tick locally in between
 *  and resync whenever the server sends a new value. */
function WaitingClock({ seconds }: { seconds: number }) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(seconds);
  const base = useRef({ seconds, at: Date.now() });
  useEffect(() => {
    base.current = { seconds, at: Date.now() };
    setShown(seconds);
  }, [seconds]);
  useEffect(() => {
    const id = setInterval(() => {
      setShown(base.current.seconds + Math.floor((Date.now() - base.current.at) / 1000));
    }, 250);
    return () => clearInterval(id);
  }, []);
  return (
    <p className="text-3xl tabular-nums" aria-live="off">
      {shown} {t("duel.seconds")}
    </p>
  );
}

export default function DuelPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";
  const { state, setState, refresh, live, failed } = useDuel(Boolean(user));
  const [rating, setRating] = useState<DuelRatingView | null>(null);
  const [history, setHistory] = useState<DuelHistoryItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const previous = useRef<string | null>(null);

  const status = state?.status ?? null;
  const lastMatch = state?.last_match_id ?? null;

  // the match ended on the server: show its result page
  useEffect(() => {
    if (previous.current === "active" && status === "idle" && lastMatch !== null) {
      navigate(`/duel/result/${lastMatch}`);
    }
    previous.current = status;
  }, [status, lastMatch, navigate]);

  useEffect(() => {
    if (status !== "idle") return;
    duelRating().then(setRating).catch(() => undefined);
    duelHistory().then(setHistory).catch(() => undefined);
  }, [status, lastMatch]);

  async function join() {
    setBusy(true);
    setMessage(null);
    try {
      setState(await duelJoin());
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) void refresh();
      else if (e instanceof ApiError && e.status === 403) setMessage(t("problem.submitErrors.blocked"));
      else setMessage(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    setBusy(true);
    try {
      await duelLeave();
    } catch {
      // already matched or not waiting any more: the refreshed state tells the truth
    } finally {
      await refresh();
      setBusy(false);
    }
  }

  if (state === null) {
    return <p className={failed ? "text-red-600" : "text-slate-500"}>{failed ? t("common.error") : t("common.loading")}</p>;
  }

  if (state.status === "active" && state.match) {
    return <DuelMatch key={state.match.id} match={state.match} uiLang={uiLang} onChanged={() => void refresh()} />;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">{t("duel.title")}</h1>
      {!live && <p className="text-xs text-amber-700">{t("duel.noLive")}</p>}

      {state.status === "waiting" ? (
        <div className="card space-y-3 text-center">
          <p className="text-lg font-semibold">{t("duel.searching")}</p>
          <WaitingClock seconds={state.waiting?.seconds ?? 0} />
          <p className="text-sm text-slate-500">{t("duel.searchingHint")}</p>
          <button className="btn-secondary" disabled={busy} onClick={() => void leave()}>
            {t("common.cancel")}
          </button>
        </div>
      ) : (
        <div className="card space-y-4">
          <p className="text-sm text-slate-600">{t("duel.rules")}</p>
          {rating && (
            <div className="grid grid-cols-2 gap-3 text-center sm:grid-cols-5">
              <div>
                <div className="text-xs text-slate-500">{t("duel.rating")}</div>
                <div className="text-2xl font-bold tabular-nums text-brand-700">{Math.round(rating.rating)}</div>
              </div>
              {(["games", "wins", "losses", "draws"] as const).map((k) => (
                <div key={k}>
                  <div className="text-xs text-slate-500">{t(`duel.${k}`)}</div>
                  <div className="text-xl font-semibold tabular-nums">{rating[k]}</div>
                </div>
              ))}
            </div>
          )}
          <button className="btn w-full sm:w-auto" disabled={busy} onClick={() => void join()}>
            {t("duel.find")}
          </button>
          {message && (
            <p role="alert" className="text-sm text-red-600">
              {message}
            </p>
          )}
          <p className="text-sm">
            <Link to="/leaderboard">{t("duel.leaderboard")}</Link>
          </p>
        </div>
      )}

      {state.status === "idle" && history.length > 0 && (
        <section className="card !p-0">
          <h2 className="px-4 pt-4 font-semibold">{t("duel.history")}</h2>
          <ul className="divide-y divide-slate-100">
            {history.map((h) => (
              <li key={h.match_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
                <Link to={`/duel/result/${h.match_id}`}>
                  #{h.match_id} · {t(`duel.outcome.${h.result}`)}
                </Link>
                <span
                  className={`tabular-nums ${
                    (h.rating_change ?? 0) > 0 ? "text-green-700" : (h.rating_change ?? 0) < 0 ? "text-red-600" : "text-slate-500"
                  }`}
                >
                  {h.rating_change === null ? "—" : `${h.rating_change > 0 ? "+" : ""}${h.rating_change}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
