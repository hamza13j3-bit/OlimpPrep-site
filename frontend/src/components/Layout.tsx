import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { LANGUAGES, isLanguage, setLanguage } from "../i18n";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2 py-1 text-sm font-medium ${isActive ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:text-slate-900"}`;

export default function Layout() {
  const { t, i18n } = useTranslation();
  const { user, logout, updateProfile } = useAuth();
  const navigate = useNavigate();

  function changeLanguage(value: string) {
    if (!isLanguage(value)) return;
    setLanguage(value);
    if (user && user.language !== value) void updateProfile({ language: value }).catch(() => undefined);
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <Link to="/problems" className="text-lg font-bold text-brand-700 no-underline">
            {t("app.name")}
          </Link>
          <nav className="flex flex-1 flex-wrap items-center gap-1">
            <NavLink to="/problems" className={navClass}>
              {t("nav.problems")}
            </NavLink>
            <NavLink to="/collections" className={navClass}>
              {t("nav.collections")}
            </NavLink>
            {user && (
              <NavLink to="/duel" className={navClass}>
                {t("nav.duel")}
              </NavLink>
            )}
            <NavLink to="/leaderboard" className={navClass}>
              {t("nav.leaderboard")}
            </NavLink>
            {user?.role === "admin" && (
              <NavLink to="/admin" className={navClass}>
                {t("nav.admin")}
              </NavLink>
            )}
            {user && (
              <NavLink to="/profile" className={navClass}>
                {t("nav.profile")}
              </NavLink>
            )}
          </nav>
          <select
            aria-label="Language"
            className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
            value={i18n.language}
            onChange={(e) => changeLanguage(e.target.value)}
          >
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l.toUpperCase()}
              </option>
            ))}
          </select>
          {user ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="hidden text-slate-600 sm:inline">{user.name}</span>
              <button
                className="btn-secondary"
                onClick={() => {
                  logout();
                  navigate("/problems");
                }}
              >
                {t("nav.logout")}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login" className="btn-secondary no-underline">
                {t("nav.login")}
              </Link>
              <Link to="/register" className="btn no-underline text-white">
                {t("nav.register")}
              </Link>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
