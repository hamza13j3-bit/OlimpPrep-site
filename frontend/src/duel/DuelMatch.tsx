import Editor from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, duelSubmit, fetchProblem, fetchSubmission } from "../api/client";
import type { CodeLanguage, DuelMatchState, Lang, ProblemPublic, SubmissionResult } from "../api/types";
import Markdown from "../components/Markdown";
import ResultBar from "../components/ResultBar";

const TEMPLATES: Record<CodeLanguage, string> = {
  python: "import sys\n\n\ndef main():\n    data = sys.stdin.read().split()\n\n\nmain()\n",
  cpp: "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n",
};
const MONACO: Record<CodeLanguage, string> = { python: "python", cpp: "cpp" };
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const draftKey = (m: number, p: number, l: CodeLanguage) => `duelcode:${m}:${p}:${l}`;
function loadDraft(m: number, p: number, l: CodeLanguage): string {
  try {
    return localStorage.getItem(draftKey(m, p, l)) ?? TEMPLATES[l];
  } catch {
    return TEMPLATES[l];
  }
}
function saveDraft(m: number, p: number, l: CodeLanguage, code: string) {
  try {
    localStorage.setItem(draftKey(m, p, l), code);
  } catch {
    // drafts just are not remembered
  }
}

export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** Counts down from the seconds the SERVER reported; the server alone decides when time is up. */
function useCountdown(remaining: number): number {
  const [left, setLeft] = useState(remaining);
  const deadline = useRef(Date.now() + remaining * 1000);
  useEffect(() => {
    deadline.current = Date.now() + remaining * 1000;
    setLeft(remaining);
  }, [remaining]);
  useEffect(() => {
    const id = setInterval(() => setLeft(Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000))), 500);
    return () => clearInterval(id);
  }, []);
  return left;
}

interface Props {
  match: DuelMatchState;
  uiLang: Lang;
  onChanged: () => void;
}

export default function DuelMatch({ match, uiLang, onChanged }: Props) {
  const { t } = useTranslation();
  const left = useCountdown(match.remaining_seconds);
  const firstOpen = match.problems.find((p) => !p.solved) ?? match.problems[0];
  const [selected, setSelected] = useState<number>(firstOpen?.problem_id ?? 0);
  const [problem, setProblem] = useState<ProblemPublic | null>(null);
  const [language, setLanguage] = useState<CodeLanguage>("python");
  const [code, setCode] = useState("");
  const [checking, setChecking] = useState(false);
  const [results, setResults] = useState<Record<number, SubmissionResult>>({});
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const current = match.problems.find((p) => p.problem_id === selected);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setProblem(null);
    fetchProblem(selected, uiLang)
      .then((p) => {
        if (!cancelled) setProblem(p);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [selected, uiLang]);

  useEffect(() => {
    setCode(loadDraft(match.id, selected, language));
    setError(null);
  }, [match.id, selected, language]);

  function onCodeChange(value: string | undefined) {
    const next = value ?? "";
    setCode(next);
    saveDraft(match.id, selected, language, next);
  }

  async function onSubmit() {
    setError(null);
    setChecking(true);
    const problemId = selected;
    try {
      const { id } = await duelSubmit(match.id, problemId, language, code);
      let final: SubmissionResult | null = null;
      for (let i = 0; i < 90 && alive.current; i++) {
        final = await fetchSubmission(id);
        if (final) break;
        await sleep(Math.min(500 + i * 150, 2000));
      }
      if (!alive.current) return;
      if (final) setResults((prev) => ({ ...prev, [problemId]: final as SubmissionResult }));
      else setError(t("problem.submitErrors.slow"));
      onChanged();
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiError && e.status === 429) setError(t("problem.submitErrors.tooMany"));
      else if (e instanceof ApiError && e.status === 409) setError(t("duel.submitClosed"));
      else setError(t("problem.submitErrors.generic"));
      onChanged();
    } finally {
      if (alive.current) setChecking(false);
    }
  }

  const urgent = left <= 300;
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs text-slate-500">{t("duel.timeLeft")}</div>
          <div className={`text-3xl font-bold tabular-nums ${urgent ? "text-red-600" : ""}`} aria-live="off">
            {formatClock(left)}
          </div>
        </div>
        <div className="flex items-center gap-6 text-center">
          <div>
            <div className="text-xs text-slate-500">{t("duel.you")}</div>
            <div className="text-2xl font-bold tabular-nums">
              {match.me.solved}/{match.me.total}
            </div>
          </div>
          <div className="text-slate-400">vs</div>
          <div>
            <div className="text-xs text-slate-500">{t("duel.opponent")}</div>
            <div className="text-2xl font-bold tabular-nums">
              {match.opponent.solved}/{match.opponent.total}
            </div>
            <div className={`text-xs ${match.opponent.connected ? "text-green-700" : "text-amber-700"}`}>
              {match.opponent.connected ? t("duel.online") : t("duel.offline")}
            </div>
          </div>
        </div>
      </div>
      <p className="text-xs text-slate-500">{t("duel.keepOpen")}</p>

      <div className="flex flex-wrap gap-2" role="tablist">
        {match.problems.map((p, i) => (
          <button
            key={p.problem_id}
            role="tab"
            aria-selected={p.problem_id === selected}
            onClick={() => setSelected(p.problem_id)}
            className={`rounded px-3 py-1.5 text-sm font-medium ${
              p.problem_id === selected ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            {String.fromCharCode(65 + i)} · #{p.number}
            {p.solved ? " ✓" : p.best_score > 0 ? ` ${Math.round(p.best_score * 100)}%` : ""}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="min-w-0 space-y-3">
          {problem === null ? (
            <p className="text-slate-500">{t("common.loading")}</p>
          ) : (
            <>
              <h2 className="text-xl font-bold">
                {problem.number}. {problem.title}
              </h2>
              <p className="text-sm text-slate-600">
                {t("problem.timeLimit")}: <b>{t("problem.ms", { value: problem.time_limit_ms })}</b> ·{" "}
                {t("problem.memoryLimit")}: <b>{t("problem.mb", { value: problem.memory_limit_mb })}</b>
              </p>
              <div className="card">
                <Markdown>{problem.statement}</Markdown>
              </div>
              {problem.examples.map((ex, i) => (
                <div key={i} className="grid gap-3 sm:grid-cols-2">
                  {(
                    [
                      ["problem.exampleInput", ex.input],
                      ["problem.exampleOutput", ex.output],
                    ] as const
                  ).map(([label, text]) => (
                    <div key={label} className="card !p-3">
                      <div className="mb-1 text-sm font-medium">{t(label)}</div>
                      <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-100 p-2 text-sm">{text}</pre>
                    </div>
                  ))}
                </div>
              ))}
            </>
          )}
        </section>

        <section className="min-w-0 space-y-3">
          <div className="card space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">{t("problem.solution")}</h2>
              <select
                aria-label={t("problem.codeLanguage")}
                className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
                value={language}
                onChange={(e) => setLanguage(e.target.value as CodeLanguage)}
                disabled={checking}
              >
                <option value="python">Python</option>
                <option value="cpp">C++</option>
              </select>
            </div>
            <div className="overflow-hidden rounded border border-slate-300">
              <Editor
                height="380px"
                language={MONACO[language]}
                value={code}
                onChange={onCodeChange}
                loading={<p className="p-3 text-sm text-slate-500">{t("common.loading")}</p>}
                options={{ minimap: { enabled: false }, fontSize: 14, automaticLayout: true, scrollBeyondLastLine: false }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                className="btn"
                disabled={checking || code.trim() === "" || current?.solved === true || left <= 0}
                onClick={() => void onSubmit()}
              >
                {checking ? t("problem.checking") : t("problem.submit")}
              </button>
              {current?.solved && <span className="text-sm font-medium text-green-700">{t("duel.alreadySolved")}</span>}
            </div>
            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
          </div>
          {results[selected] && <ResultBar result={results[selected]} />}
        </section>
      </div>
    </div>
  );
}
