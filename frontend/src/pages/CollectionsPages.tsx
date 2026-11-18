import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError, fetchCollection, fetchCollections } from "../api/client";
import type { CollectionBrief, CollectionDetail, Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ProblemsTable from "../components/ProblemsTable";
import { isLanguage } from "../i18n";

export function CollectionsPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<CollectionBrief[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchCollections()
      .then(setItems)
      .catch(() => setError(true));
  }, []);

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">{t("collections.title")}</h1>
      {error ? (
        <p className="text-red-600">{t("common.error")}</p>
      ) : items === null ? (
        <p className="text-slate-500">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="text-slate-500">{t("collections.empty")}</p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((c) => (
            <li key={c.id} className="card">
              <Link to={`/collections/${c.id}`} className="text-lg font-semibold">
                {c.title}
              </Link>
              {c.description && <p className="mt-1 text-sm text-slate-600">{c.description}</p>}
              <p className="mt-2 text-sm text-slate-500">{t("collections.count", { count: c.problem_count })}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CollectionDetailPage() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const [data, setData] = useState<CollectionDetail | null>(null);
  const [error, setError] = useState<"missing" | "failed" | null>(null);
  const uiLang: Lang = isLanguage(i18n.language) ? i18n.language : "kk";

  useEffect(() => {
    const n = Number(id);
    if (!Number.isInteger(n)) {
      setError("missing");
      return;
    }
    setError(null);
    fetchCollection(n, uiLang)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof ApiError && e.status === 404 ? "missing" : "failed"));
  }, [id, uiLang, user?.id]);

  if (error === "missing") return <p>{t("common.notFound")}</p>;
  if (error === "failed") return <p className="text-red-600">{t("common.error")}</p>;
  if (data === null) return <p className="text-slate-500">{t("common.loading")}</p>;

  return (
    <div>
      <Link to="/collections" className="text-sm">
        ← {t("collections.title")}
      </Link>
      <h1 className="mb-1 mt-2 text-2xl font-bold">{data.title}</h1>
      {data.description && <p className="mb-3 text-slate-600">{data.description}</p>}
      {data.problems.length === 0 ? (
        <p className="text-slate-500">{t("archive.empty")}</p>
      ) : (
        <ProblemsTable items={data.problems} />
      )}
    </div>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return <p className="text-center text-slate-600">{t("common.notFound")}</p>;
}
