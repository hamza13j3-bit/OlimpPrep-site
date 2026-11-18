import { useTranslation } from "react-i18next";

interface Props {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, pages, onChange }: Props) {
  const { t } = useTranslation();
  if (pages <= 1) return null;
  return (
    <nav className="mt-4 flex items-center justify-center gap-3" aria-label="pagination">
      <button className="btn-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ← {t("common.prev")}
      </button>
      <span className="text-sm text-slate-600">{t("archive.page", { page, pages })}</span>
      <button className="btn-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        {t("common.next")} →
      </button>
    </nav>
  );
}
