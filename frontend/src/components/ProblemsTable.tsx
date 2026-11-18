import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { ArchiveItem } from "../api/types";
import StatusIcon from "./StatusIcon";
import TagChip from "./TagChip";

export type SortKey = "number" | "rating" | "solved";
export const DEFAULT_ORDER: Record<string, "asc" | "desc"> = { number: "asc", rating: "asc", solved: "desc", newest: "desc" };

interface Props {
  items: ArchiveItem[];
  /** When given, the #, rating and solved headers become sortable. */
  sort?: { key: string; order: "asc" | "desc"; onSort: (key: SortKey) => void };
  onTagClick?: (slug: string) => void;
}

export default function ProblemsTable({ items, sort, onTagClick }: Props) {
  const { t } = useTranslation();

  function header(key: SortKey, label: string, extra = "") {
    const active = sort?.key === key;
    const arrow = active ? (sort?.order === "asc" ? " ▲" : " ▼") : "";
    return (
      <th
        scope="col"
        className={`px-3 py-2 text-left font-semibold ${extra}`}
        aria-sort={active ? (sort?.order === "asc" ? "ascending" : "descending") : undefined}
      >
        {sort ? (
          <button type="button" className="font-semibold hover:text-brand-600" onClick={() => sort.onSort(key)}>
            {label}
            {arrow}
          </button>
        ) : (
          label
        )}
      </th>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-100 text-slate-700">
          <tr>
            {header("number", t("archive.columns.number"), "w-16")}
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              {t("archive.columns.title")}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-left font-semibold md:table-cell">
              {t("archive.columns.tags")}
            </th>
            {header("rating", t("archive.columns.rating"), "w-24")}
            {header("solved", t("archive.columns.solved"), "w-24")}
            <th scope="col" className="w-12 px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((p) => (
            <tr key={p.number} className="hover:bg-slate-50">
              <td className="px-3 py-2 text-slate-500">{p.number}</td>
              <td className="px-3 py-2">
                <Link to={`/problems/${p.number}`} className="font-medium">
                  {p.title}
                </Link>
                <div className="mt-1 flex flex-wrap gap-1 md:hidden">
                  {p.tags.map((tag) => (
                    <TagChip key={tag} slug={tag} />
                  ))}
                </div>
              </td>
              <td className="hidden px-3 py-2 md:table-cell">
                <div className="flex flex-wrap gap-1">
                  {p.tags.map((tag) => (
                    <TagChip key={tag} slug={tag} onClick={onTagClick ? () => onTagClick(tag) : undefined} />
                  ))}
                </div>
              </td>
              <td className="px-3 py-2 tabular-nums">{p.rating}</td>
              <td className="px-3 py-2 tabular-nums text-slate-600">× {p.solved_count}</td>
              <td className="px-3 py-2">
                <StatusIcon status={p.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
