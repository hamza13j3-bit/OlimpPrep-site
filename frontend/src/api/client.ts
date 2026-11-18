import type {
  AdminStats,
  AdminUser,
  AdminUsersPage,
  ArchivePage,
  AuditPage,
  CodeLanguage,
  CollectionBrief,
  CollectionDetail,
  DuelHistoryItem,
  DuelRatingView,
  DuelResult,
  DuelState,
  HintRevealed,
  HistoryPoint,
  Lang,
  LeaderPage,
  ProblemPublic,
  ProblemSummary,
  RatingCorrection,
  RatingOut,
  StatsOut,
  SubmissionResult,
  TagOut,
  TokenOut,
  User,
} from "./types";

const BASE = "/api"; // Vite proxies /api to the FastAPI server
const TOKEN_KEY = "token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage blocked: the session just will not survive a reload
  }
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length) params.set(key, value.join(","));
    } else {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return `${BASE}${path}${qs ? `?${qs}` : ""}`;
}

async function raw(path: string, init: { method?: string; body?: unknown; query?: Query; signal?: AbortSignal } = {}) {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(buildUrl(path, init.query), {
    method: init.method ?? "GET",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      // body was not JSON
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

async function request<T>(path: string, init?: Parameters<typeof raw>[1]): Promise<T> {
  const res = await raw(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

// ---- auth ----
export const login = (email: string, password: string) =>
  request<TokenOut>("/auth/login", { method: "POST", body: { email, password } });
export const register = (body: { email: string; password: string; name: string; school_group: string; language: Lang }) =>
  request<TokenOut>("/auth/register", { method: "POST", body });
export const fetchMe = () => request<User>("/auth/me");
export const updateMe = (body: Partial<Pick<User, "name" | "school_group" | "language">>) =>
  request<User>("/auth/me", { method: "PATCH", body });

// ---- archive ----
export interface ArchiveQuery {
  tags: string[];
  rating_min?: number;
  rating_max?: number;
  status?: string;
  source?: string;
  year?: number;
  lang?: string;
  q?: string;
  sort: string;
  order?: string;
  page: number;
  ui_lang: Lang;
}
export const fetchArchive = (q: ArchiveQuery, signal?: AbortSignal) =>
  request<ArchivePage>("/archive/problems", { query: { ...q }, signal });
export const fetchTags = () => request<TagOut[]>("/tags");

export const fetchCollections = () => request<CollectionBrief[]>("/collections");
export const fetchCollection = (id: number, ui_lang: Lang) =>
  request<CollectionDetail>(`/collections/${id}`, { query: { ui_lang } });

// ---- problem ----
export const fetchProblem = (id: number, lang: Lang) => request<ProblemPublic>(`/problems/${id}`, { query: { lang } });
export const fetchSummary = (id: number) => request<ProblemSummary>(`/submissions/problem/${id}/summary`);
export const fetchOpenedHints = (id: number, lang: Lang) =>
  request<HintRevealed[]>(`/problems/${id}/hints`, { query: { lang } });
export const openHint = (id: number, level: number, lang: Lang) =>
  request<HintRevealed>(`/problems/${id}/hints/${level}`, { method: "POST", query: { lang } });

export const submitSolution = (problem_id: number, language: CodeLanguage, code: string) =>
  request<{ id: number }>("/submissions", { method: "POST", body: { problem_id, language, code } });

/** Returns the result, or null while the server is still checking (HTTP 202). */
export async function fetchSubmission(id: number): Promise<SubmissionResult | null> {
  const res = await raw(`/submissions/${id}`);
  if (res.status === 202) return null;
  return (await res.json()) as SubmissionResult;
}

// ---- rating ----
export const fetchRating = () => request<RatingOut>("/rating/me");
export const fetchHistory = (tag?: string) => request<HistoryPoint[]>("/rating/me/history", { query: { tag } });

// ---- stats ----
export const fetchStats = (lang: Lang) => request<StatsOut>("/stats/me", { query: { lang } });
// ---- leaderboards ----
export const fetchLeaderboard = (board: "global" | "duel" | { tag: string }, page: number) =>
  request<LeaderPage>(typeof board === "string" ? `/leaderboards/${board}` : `/leaderboards/tag/${board.tag}`, {
    query: { page },
  });

// ---- admin ----
export const adminUsers = (q: string, page: number) => request<AdminUsersPage>("/admin/users", { query: { q, page } });
export const adminBlock = (id: number, blocked: boolean) =>
  request<AdminUser>(`/admin/users/${id}/block`, { method: "PATCH", body: { blocked } });
export const adminPromote = (id: number) => request<AdminUser>(`/admin/users/${id}/promote`, { method: "POST" });
export const adminCorrectRating = (id: number, body: RatingCorrection) =>
  request<{ old_rating: number; new_rating: number }>(`/admin/users/${id}/rating`, { method: "POST", body });
export const adminStats = (lang: Lang) => request<AdminStats>("/admin/stats", { query: { lang } });
export const adminAudit = (page: number) => request<AuditPage>("/admin/audit", { query: { page } });
// ---- duel ----
export const duelState = () => request<DuelState>("/duel/me");
export const duelJoin = () => request<DuelState>("/duel/queue", { method: "POST" });
export const duelLeave = () => request<void>("/duel/queue", { method: "DELETE" });
export const duelRating = () => request<DuelRatingView>("/duel/rating");
export const duelHistory = () => request<DuelHistoryItem[]>("/duel/matches");
export const duelResult = (id: number, lang: Lang) => request<DuelResult>(`/duel/matches/${id}/result`, { query: { lang } });
export const duelSubmit = (matchId: number, problem_id: number, language: CodeLanguage, code: string) =>
  request<{ id: number }>(`/duel/matches/${matchId}/submit`, { method: "POST", body: { problem_id, language, code } });