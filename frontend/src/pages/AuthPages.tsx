import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import type { Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { isLanguage } from "../i18n";

function useAfterAuth() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/problems";
  return () => navigate(from, { replace: true });
}

function errorKey(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return "auth.errors.blocked";
    if (e.status === 409) return "auth.errors.taken";
    if (e.status === 401) return "auth.errors.invalid";
    if (e.status === 422) return "auth.errors.validation";
  }
  return "common.error";
}

export function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const done = useAfterAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      done();
    } catch (err) {
      setError(errorKey(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-4 text-2xl font-bold">{t("auth.loginTitle")}</h1>
      <form onSubmit={submit} className="card space-y-4">
        <label className="block text-sm font-medium">
          {t("auth.email")}
          <input className="input mt-1" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          {t("auth.password")}
          <input className="input mt-1" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {t(error)}
          </p>
        )}
        <button className="btn w-full" disabled={busy}>
          {t("nav.login")}
        </button>
      </form>
      <p className="mt-4 text-center text-sm">
        {t("auth.noAccount")} <Link to="/register">{t("nav.register")}</Link>
      </p>
    </div>
  );
}

export function RegisterPage() {
  const { t, i18n } = useTranslation();
  const { register } = useAuth();
  const done = useAfterAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const language: Lang = isLanguage(i18n.language) ? i18n.language : "kk";
    try {
      await register({ email: email.trim(), password, name: name.trim(), school_group: "", language });
      done();
    } catch (err) {
      setError(errorKey(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-4 text-2xl font-bold">{t("auth.registerTitle")}</h1>
      <form onSubmit={submit} className="card space-y-4">
        <label className="block text-sm font-medium">
          {t("auth.name")}
          <input className="input mt-1" required maxLength={100} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          {t("auth.email")}
          <input className="input mt-1" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block text-sm font-medium">
          {t("auth.password")}
          <input className="input mt-1" type="password" autoComplete="new-password" required minLength={8} maxLength={72} value={password} onChange={(e) => setPassword(e.target.value)} />
          <span className="mt-1 block text-xs font-normal text-slate-500">{t("auth.passwordHint")}</span>
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {t(error)}
          </p>
        )}
        <button className="btn w-full" disabled={busy}>
          {t("nav.register")}
        </button>
      </form>
      <p className="mt-4 text-center text-sm">
        {t("auth.haveAccount")} <Link to="/login">{t("nav.login")}</Link>
      </p>
    </div>
  );
}
