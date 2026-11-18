import { useTranslation } from "react-i18next";

import type { Status } from "../api/types";

export default function StatusIcon({ status }: { status: Status | null }) {
  const { t } = useTranslation();
  if (status === null) return null; // anonymous visitor: no personal status
  const label = t(`archive.statusIcon.${status}`);
  const look = {
    solved: { symbol: "✓", cls: "bg-green-100 text-green-700" },
    attempted: { symbol: "!", cls: "bg-amber-100 text-amber-700" },
    unsolved: { symbol: "", cls: "border border-slate-300 text-transparent" },
  }[status];
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-sm font-bold ${look.cls}`}
    >
      {look.symbol || "·"}
    </span>
  );
}
