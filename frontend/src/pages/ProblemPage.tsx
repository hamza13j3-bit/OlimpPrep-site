import Editor from "@monaco-editor/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  ApiError,
  fetchOpenedHints,
  fetchProblem,
  fetchSubmission,
  fetchSummary,
  openHint,
  submitSolution,
} from "../api/client";
import type { CodeLanguage, Lang, ProblemPublic, ProblemSummary, SubmissionResult } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Markdown from "../components/Markdown";
import ResultBar from "../components/ResultBar";
import TagChip from "../components/TagChip";
import { isLanguage } from "../i18n";

const TEMPLATES: Record<CodeLanguage, string> = {
  python: "import sys\n\n\ndef main():\n    data = sys.stdin.read().split()\n\n\nmain()\n",
  cpp: "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n",
};
const MONACO: Record<CodeLanguage, string> = { python: "python", cpp: "cpp" };

const codeKey = (id: number, lang: CodeLanguage) => `code:${id}:${lang}`;

function loadCode(id: number, lang: CodeLanguage): string {
  try {
    return localStorage.getItem(codeKey(id, lang)) ?? TEMPLATES[lang];
  } catch {
    return TEMPLATES[lang];
  }
}

function saveCode(id: number, lang: CodeLanguage, code: string) {
  try {
    localStorage.setItem(codeKey(id, lang), code);
  } catch {
    // storage unavailable: the draft just is not remembered
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button type="button" className="btn-secondary !py-0.5 text-xs" onClick={() => void copy()}>
      {copied ? t("common.copied") : t("common.copy")}
    </button>
  );
}

export default function ProblemPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const params = useParams();
  const id = Number(params.id);
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";

  const [problem, setProblem] = useState<ProblemPublic | null>(null);
  const [loadError, setLoadError] = useState<"missing" | "failed" | null>(null);
  const [summary, setSummary] = useState<ProblemSummary | null>(null);
  const [hints, setHints] = useState<Record<number, string>>({});
  const [hintError, setHintError] = useState<string | null>(null);
  const [language, setLanguage] = useState<CodeLanguage>("python");
  const [code, setCode] = useState("");
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const loadProblem = useCallback(() => {
    if (!Number.isInteger(id)) {
      setLoadError("missing");
      return Promise.resolve();
    }
    return fetchProblem(id, uiLang)
      .then((p) => {
        setProblem(p);
        setLoadError(null);
      })
      .catch((e: unknown) => setLoadError(e instanceof ApiError && e.status === 404 ? "missing" : "failed"));
  }, [id, uiLang]);

  const loadSummary = useCallback(() => {
    if (!Number.isInteger(id)) return;
    fetchSummary(id)
      .then(setSummary)
      .catch(() => undefined);
  }, [id]);

  // statement (re-fetched when the interface language or the login state changes)
  useEffect(() => {
    void loadProblem();
  }, [loadProblem, user?.id]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary, user?.id]);

  // hints already opened by this user
  useEffect(() => {
    setHints({});
    if (!user || !Number.isInteger(id)) return;
    fetchOpenedHints(id, uiLang)
      .then((list) => setHints(Object.fromEntries(list.map((h) => [h.level, h.text]))))
      .catch(() => undefined);
  }, [id, uiLang, user]);

  // editor draft per problem and language
  useEffect(() => {
    setCode(loadCode(id, language));
    setResult(null);
    setSubmitError(null);
  }, [id, language]);

  function onCodeChange(value: string | undefined) {
    const next = value ?? "";
    setCode(next);
    saveCode(id, language, next);
  }

  async function onOpenHint(level: number) {
    setHintError(null);
    try {
      const h = await openHint(id, level, uiLang);
      setHints((prev) => ({ ...prev, [h.level]: h.text }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setHintError(t("problem.hintLogin"));
      else if (e instanceof ApiError && e.status === 404) setHintError(t("problem.hintUnavailable"));
      else if (e instanceof ApiError && e.status === 403) setHintError(t("problem.submitErrors.blocked"));
      else setHintError(t("common.error"));
    }
  }

  async function onSubmit() {
    setSubmitError(null);
    setResult(null);
    setChecking(true);
    try {
      const { id: submissionId } = await submitSolution(id, language, code);
      let final: SubmissionResult | null = null;
      for (let attempt = 0; attempt < 90 && alive.current; attempt++) {
        final = await fetchSubmission(submissionId);
        if (final) break;
        await sleep(Math.min(500 + attempt * 150, 2000));
      }
      if (!alive.current) return;
      if (final) {
        setResult(final);
        loadSummary();
        if (final.solved) void loadProblem(); // solving unlocks hidden tags
      } else {
        setSubmitError(t("problem.submitErrors.slow"));
      }
    } catch (e) {
      if (!alive.current) return;
      if (e instanceof ApiError && e.status === 429) setSubmitError(t("problem.submitErrors.tooMany"));
      else if (e instanceof ApiError && e.status === 403) setSubmitError(t("problem.submitErrors.blocked"));
      else setSubmitError(t("problem.submitErrors.generic"));
    } finally {
      if (alive.current) setChecking(false);
    }
  }

  if (loadError === "missing") return <p>{t("common.notFound")}</p>;
  if (loadError === "failed") {
    return (
      <div className="card text-center">
        <p className="mb-3 text-red-600">{t("common.error")}</p>
        <button className="btn" onClick={() => void loadProblem()}>
          {t("common.retry")}
        </button>
      </div>
    );
  }
  if (problem === null) return <p className="text-slate-500">{t("common.loading")}</p>;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="min-w-0 space-y-4">
        <Link to="/problems" className="text-sm">
          ← {t("nav.problems")}
        </Link>
        <h1 className="text-2xl font-bold">
          {problem.number}. {problem.title}
        </h1>

        <div className="card flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-700">
          <span>
            {t("problem.timeLimit")}: <b>{t("problem.ms", { value: problem.time_limit_ms })}</b>
          </span>
          <span>
            {t("problem.memoryLimit")}: <b>{t("problem.mb", { value: problem.memory_limit_mb })}</b>
          </span>
          <span>
            {t("archive.columns.rating")}: <b>{problem.rating}</b>
          </span>
          {summary && (
            <span className="font-medium text-green-700">{t("problem.solvedBy", { count: summary.solved_count })}</span>
          )}
          {user && summary && (
            <span>{t("problem.bestScore", { score: Math.round(summary.best_score * 100) })}</span>
          )}
        </div>

        <div className="card">
          <Markdown>{problem.statement}</Markdown>
        </div>

        {problem.examples.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">{t("problem.examples")}</h2>
            {problem.examples.map((ex, i) => (
              <div key={i} className="grid gap-3 sm:grid-cols-2">
                {(
                  [
                    ["problem.exampleInput", ex.input],
                    ["problem.exampleOutput", ex.output],
                  ] as const
                ).map(([label, text]) => (
                  <div key={label} className="card !p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-medium">{t(label)}</span>
                      <CopyButton text={text} />
                    </div>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-100 p-2 text-sm">{text}</pre>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        <div className="card text-sm">
          {problem.tags_hidden ? (
            <p className="text-slate-500">{t("problem.tagsHidden")}</p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t("problem.tags")}:</span>
              {problem.tags.map((tag) => (
                <TagChip key={tag} slug={tag} />
              ))}
            </div>
          )}
          {(problem.source || problem.author || problem.year) && (
            <p className="mt-2 text-slate-600">
              {[problem.source, problem.author, problem.year].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      </section>

      <section className="min-w-0 space-y-4">
        <div className="card space-y-2">
          <h2 className="font-semibold">{t("problem.hints")}</h2>
          <p className="text-xs text-slate-500">{t("problem.hintWarning")}</p>
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3].map((level) => (
              <button
                key={level}
                className="btn-secondary"
                disabled={level in hints}
                onClick={() => void onOpenHint(level)}
                title={t(`problem.hintLevels.${level}`)}
              >
                {t("problem.hintLevel", { level })}
              </button>
            ))}
          </div>
          {hintError && (
            <p role="alert" className="text-sm text-red-600">
              {hintError}
            </p>
          )}
          {Object.entries(hints)
            .sort(([a], [b]) => Number(a) - Number(b))
            .map(([level, text]) => (
              <div key={level} className="rounded border-l-4 border-brand-500 bg-brand-50 p-2 text-sm">
                <div className="font-medium">{t(`problem.hintLevels.${level}`)}</div>
                <div className="whitespace-pre-wrap">{text}</div>
              </div>
            ))}
        </div>

        {!user ? (
          <div className="card text-sm">
            <Link to="/login" state={{ from: `/problems/${id}` }}>
              {t("problem.loginToSubmit")}
            </Link>
          </div>
        ) : (
        <div className="card space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">{t("problem.solution")}</h2>
            <label className="flex items-center gap-2 text-sm">
              {t("problem.codeLanguage")}
              <select
                className="rounded border border-slate-300 bg-white px-2 py-1"
                value={language}
                onChange={(e) => setLanguage(e.target.value as CodeLanguage)}
                disabled={checking}
              >
                <option value="python">Python</option>
                <option value="cpp">C++</option>
              </select>
            </label>
          </div>
          <div className="overflow-hidden rounded border border-slate-300">
            <Editor
              height="420px"
              language={MONACO[language]}
              value={code}
              onChange={onCodeChange}
              loading={<p className="p-3 text-sm text-slate-500">{t("common.loading")}</p>}
              options={{ minimap: { enabled: false }, fontSize: 14, automaticLayout: true, scrollBeyondLastLine: false }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn" disabled={checking || code.trim() === ""} onClick={() => void onSubmit()}>
              {checking ? t("problem.checking") : t("problem.submit")}
            </button>
          </div>
        </div>
        )}
        {submitError && (
          <p role="alert" className="text-sm text-red-600">
            {submitError}
          </p>
        )}

        {result && <ResultBar result={result} />}
      </section>
    </div>
  );
}
