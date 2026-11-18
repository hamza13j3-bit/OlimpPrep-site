import { useTranslation } from "react-i18next";

import type { SubmissionResult } from "../api/types";

/** Shows only what the server reports: tests passed / total, score, solved. */
export default function ResultBar({ result }: { result: SubmissionResult }) {
  const { t } = useTranslation();
  const ratio = result.tests_total > 0 ? result.tests_passed / result.tests_total : 0;
  const color = result.solved ? "bg-green-500" : ratio > 0 ? "bg-amber-500" : "bg-slate-400";
  return (
    <div className="card" aria-live="polite">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-semibold">
          {t("problem.result.tests", { passed: result.tests_passed, total: result.tests_total })}
        </span>
        <span className="text-sm text-slate-600">{t("problem.result.score", { score: Math.round(result.score * 100) })}</span>
      </div>
      <div
        className="h-3 w-full overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={result.tests_total}
        aria-valuenow={result.tests_passed}
      >
        <div className={`h-full ${color} transition-all`} style={{ width: `${Math.round(ratio * 100)}%` }} />
      </div>
      {result.solved && <p className="mt-2 font-medium text-green-700">{t("problem.result.solved")}</p>}
    </div>
  );
}
