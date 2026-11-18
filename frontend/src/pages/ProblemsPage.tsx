import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchArchive, fetchTags } from "../api/client";
import type { ArchivePage, Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Pagination from "../components/Pagination";
import ProblemsTable, { DEFAULT_ORDER, type SortKey } from "../components/ProblemsTable";
import TagChip from "../components/TagChip";
import { isLanguage } from "../i18n";

const SORTS = ["number", "rating", "solved", "newest"] as const;
type SortName = (typeof SORTS)[number];

function intParam(v: string | null): number | undefined {
  if (v === null || v === "") return undefined;
  const n = Number(v);
  return Number.isInteger(n) ? n : undefined;
}

/** All filters live in the URL, so the page can be shared, bookmarked and used with Back. */
export default function ProblemsPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [allTags, setAllTags] = useState<string[]>([]);
  const [data, setData] = useState<ArchivePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const [qInput, setQInput] = useState(params.get("q") ?? "");
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";

  const tags = (params.get("tags") ?? "").split(",").filter(Boolean);
  const sortParam = params.get("sort");
  const sort: SortName = (SORTS as readonly string[]).includes(sortParam ?? "") ? (sortParam as SortName) : "number";
  const orderParam = params.get("order");
  const order: "asc" | "desc" = orderParam === "asc" || orderParam === "desc" ? orderParam : DEFAULT_ORDER[sort];
  const page = Math.max(1, intParam(params.get("page")) ?? 1);

  function update(patch: Record<string, string | undefined>, opts: { keepPage?: boolean; replace?: boolean } = {}) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!opts.keepPage && !("page" in patch)) next.delete("page");
    if (next.get("page") === "1") next.delete("page");
    setParams(next, { replace: opts.replace ?? false });
  }

  // debounce the search box into the URL
  useEffect(() => {
    const timer = setTimeout(() => {
      if ((params.get("q") ?? "") !== qInput.trim()) update({ q: qInput.trim() }, { replace: true });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  useEffect(() => {
    fetchTags()
      .then((list) => setAllTags(list.map((x) => x.slug)))
      .catch(() => undefined);
  }, []);

  const query = params.toString();
  useEffect(() => {
    const p = new URLSearchParams(query);
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetchArchive(
      {
        tags: (p.get("tags") ?? "").split(",").filter(Boolean),
        rating_min: intParam(p.get("rating_min")),
        rating_max: intParam(p.get("rating_max")),
        status: p.get("status") ?? undefined,
        source: p.get("source") ?? undefined,
        year: intParam(p.get("year")),
        lang: p.get("lang") ?? undefined,
        q: p.get("q") ?? undefined,
        sort,
        order: p.get("order") ?? undefined,
        page,
        ui_lang: uiLang,
      },
      controller.signal,
    )
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(true);
        setLoading(false);
      });
    return () => controller.abort();
  }, [query, sort, page, uiLang, user?.id, retryTick]);

  function toggleTag(slug: string) {
    const next = tags.includes(slug) ? tags.filter((x) => x !== slug) : [...tags, slug];
    update({ tags: next.join(",") });
  }

  function onSort(key: SortKey) {
    if (key === sort) update({ sort: key, order: order === "asc" ? "desc" : "asc" });
    else update({ sort: key, order: undefined });
  }

  function reset() {
    setQInput("");
    setParams(new URLSearchParams());
  }

  const hasFilters = params.toString() !== "";

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{t("archive.title")}</h1>
        <button className="btn-secondary md:hidden" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
          {t("archive.filters")}
        </button>
      </div>

      <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
        <aside className={`${showFilters ? "block" : "hidden"} card h-fit space-y-4 md:block`}>
          <label className="block text-sm font-medium">
            {t("archive.search")}
            <input className="input mt-1" type="search" value={qInput} onChange={(e) => setQInput(e.target.value)} />
          </label>
          <div>
            <div className="mb-1 text-sm font-medium">{t("archive.tags")}</div>
            <div className="flex flex-wrap gap-1">
              {allTags.map((slug) => (
                <TagChip key={slug} slug={slug} selected={tags.includes(slug)} onClick={() => toggleTag(slug)} />
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm font-medium">
              {t("archive.ratingMin")}
              <input className="input mt-1" type="number" min={0} value={params.get("rating_min") ?? ""} onChange={(e) => update({ rating_min: e.target.value })} />
            </label>
            <label className="block text-sm font-medium">
              {t("archive.ratingMax")}
              <input className="input mt-1" type="number" min={0} value={params.get("rating_max") ?? ""} onChange={(e) => update({ rating_max: e.target.value })} />
            </label>
          </div>
          {user && (
            <label className="block text-sm font-medium">
              {t("archive.status")}
              <select className="input mt-1" value={params.get("status") ?? ""} onChange={(e) => update({ status: e.target.value })}>
                <option value="">{t("archive.statuses.all")}</option>
                <option value="solved">{t("archive.statuses.solved")}</option>
                <option value="attempted">{t("archive.statuses.attempted")}</option>
                <option value="unsolved">{t("archive.statuses.unsolved")}</option>
              </select>
            </label>
          )}
          <label className="block text-sm font-medium">
            {t("archive.source")}
            <input className="input mt-1" value={params.get("source") ?? ""} onChange={(e) => update({ source: e.target.value }, { replace: true })} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm font-medium">
              {t("archive.year")}
              <input className="input mt-1" type="number" value={params.get("year") ?? ""} onChange={(e) => update({ year: e.target.value })} />
            </label>
            <label className="block text-sm font-medium">
              {t("archive.language")}
              <select className="input mt-1" value={params.get("lang") ?? ""} onChange={(e) => update({ lang: e.target.value })}>
                <option value="">—</option>
                <option value="kk">KK</option>
                <option value="ru">RU</option>
                <option value="en">EN</option>
              </select>
            </label>
          </div>
          <label className="block text-sm font-medium">
            {t("archive.sort")}
            <select className="input mt-1" value={sort} onChange={(e) => update({ sort: e.target.value, order: undefined })}>
              <option value="number">{t("archive.columns.number")}</option>
              <option value="rating">{t("archive.columns.rating")}</option>
              <option value="solved">{t("archive.columns.solved")}</option>
              <option value="newest">{t("archive.sortNewest")}</option>
            </select>
          </label>
          {hasFilters && (
            <button className="btn-secondary w-full" onClick={reset}>
              {t("common.reset")}
            </button>
          )}
        </aside>

        <section aria-busy={loading}>
          {error ? (
            <div className="card text-center">
              <p className="mb-3 text-red-600">{t("common.error")}</p>
              <button className="btn" onClick={() => setRetryTick((n) => n + 1)}>
                {t("common.retry")}
              </button>
            </div>
          ) : data === null ? (
            <p className="text-slate-500">{t("common.loading")}</p>
          ) : (
            <div className={loading ? "opacity-60" : undefined}>
              <p className="mb-2 text-sm text-slate-600">{t("archive.total", { count: data.total })}</p>
              {data.items.length === 0 ? (
                <p className="card text-center text-slate-500">{t("archive.empty")}</p>
              ) : (
                <ProblemsTable items={data.items} sort={{ key: sort, order, onSort }} onTagClick={toggleTag} />
              )}
              <Pagination page={data.page} pages={data.pages} onChange={(p) => update({ page: String(p) })} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
