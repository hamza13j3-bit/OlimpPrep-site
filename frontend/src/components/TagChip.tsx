import { useTranslation } from "react-i18next";

interface Props {
  slug: string;
  selected?: boolean;
  onClick?: () => void;
}

export default function TagChip({ slug, selected = false, onClick }: Props) {
  const { t } = useTranslation();
  const label = t(`tags.${slug}`, { defaultValue: slug });
  const base = "inline-block rounded-full border px-2 py-0.5 text-xs";
  const color = selected
    ? "border-brand-600 bg-brand-600 text-white"
    : "border-slate-300 bg-slate-100 text-slate-700";
  if (!onClick) return <span className={`${base} ${color}`}>{label}</span>;
  return (
    <button type="button" aria-pressed={selected} onClick={onClick} className={`${base} ${color} hover:border-brand-500`}>
      {label}
    </button>
  );
}
