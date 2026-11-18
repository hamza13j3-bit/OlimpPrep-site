import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  if (loading) return <p className="text-slate-500">{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
