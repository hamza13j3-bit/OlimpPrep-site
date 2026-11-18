import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import { CollectionDetailPage, CollectionsPage, NotFoundPage } from "./pages/CollectionsPages";
import ProblemsPage from "./pages/ProblemsPage";

// Heavy pages (Monaco, KaTeX, charts) are loaded on demand to keep the first load small.
const ProblemPage = lazy(() => import("./pages/ProblemPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const LeaderboardPage = lazy(() => import("./pages/LeaderboardPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const DuelPage = lazy(() => import("./pages/DuelPage"));
const DuelResultPage = lazy(() => import("./pages/DuelResultPage"));

export default function App() {
  const { t } = useTranslation();
  return (
    <Suspense fallback={<p className="p-6 text-slate-500">{t("common.loading")}</p>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/problems" replace />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route path="problems" element={<ProblemsPage />} />
          <Route path="problems/:id" element={<ProblemPage />} />
          <Route path="collections" element={<CollectionsPage />} />
          <Route path="collections/:id" element={<CollectionDetailPage />} />
          <Route
            path="profile"
            element={
              <RequireAuth>
                <ProfilePage />
              </RequireAuth>
            }
          />
          <Route path="duel" element={<RequireAuth><DuelPage /></RequireAuth>} />
          <Route path="duel/result/:id" element={<RequireAuth><DuelResultPage /></RequireAuth>} />
          <Route path="leaderboard" element={<LeaderboardPage />} />
          <Route
            path="admin"
            element={
              <RequireAuth>
                <AdminPage />
              </RequireAuth>
            }
          />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
