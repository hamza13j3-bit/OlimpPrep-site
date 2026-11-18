export type Lang = "kk" | "ru" | "en";
export type Status = "solved" | "attempted" | "unsolved";

export interface User {
  id: number;
  email: string;
  name: string;
  school_group: string;
  language: Lang;
  role: "user" | "admin";
  is_blocked: boolean;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ArchiveItem {
  number: number;
  title: string;
  lang: string;
  languages: string[];
  tags: string[];
  tags_hidden: boolean;
  rating: number;
  solved_count: number;
  status: Status | null;
  source: string;
  year: number | null;
}

export interface ArchivePage {
  items: ArchiveItem[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
}

export interface TagOut {
  slug: string;
}

export interface CollectionBrief {
  id: number;
  title: string;
  description: string;
  problem_count: number;
}

export interface CollectionDetail {
  id: number;
  title: string;
  description: string;
  problems: ArchiveItem[];
}

export interface Example {
  input: string;
  output: string;
}

export interface ProblemPublic {
  id: number;
  number: number;
  rating: number;
  time_limit_ms: number;
  memory_limit_mb: number;
  source: string;
  year: number | null;
  author: string;
  tags: string[];
  tags_hidden: boolean;
  lang: Lang;
  languages: Lang[];
  title: string;
  statement: string;
  examples: Example[];
}

export interface HintRevealed {
  level: number;
  text: string;
}

export type CodeLanguage = "python" | "cpp";

/** The only things the server ever reports about a checked submission. */
export interface SubmissionResult {
  id: number;
  tests_passed: number;
  tests_total: number;
  score: number;
  solved: boolean;
}

export interface ProblemSummary {
  solved_count: number;
  best_score: number;
}

export interface TagRating {
  tag: string;
  rating: number;
  attempts: number;
}

export interface RatingOut {
  rating: number;
  attempts: number;
  tags: TagRating[];
}

export interface HistoryPoint {
  submission_id: number;
  problem_id: number;
  old_rating: number;
  new_rating: number;
  created_at: string;
}

export interface TagStat {
  tag: string;
  avg_score: number; // 0..1
  attempted: number;
  solved: number;
}

export interface RetryItem {
  problem_id: number;
  title: string;
  best_score: number;
  stage: number; // 0..3 -> after 1, 3, 7, 14 days
  due: boolean;
  next_due_at: string;
}

export interface StatsOut {
  tags: TagStat[];
  retry: RetryItem[];
}

export interface LeaderRow {
  rank: number;
  user_id: number;
  name: string;
  rating: number;
  solved: number;
  is_me: boolean;
}

export interface MyPosition {
  rank: number;
  position: number;
  page: number;
  rating: number;
  solved: number;
}

export interface LeaderPage {
  items: LeaderRow[];
  total: number;
  page: number;
  page_size: number;
  me: MyPosition | null;
}

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  school_group: string;
  role: "user" | "admin";
  is_blocked: boolean;
  created_at: string;
  rating: number | null;
}

export interface AdminUsersPage {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProblemCount {
  problem_id: number;
  title: string;
  solved: number;
}

export interface AdminStats {
  users_total: number;
  users_blocked: number;
  admins: number;
  submissions_total: number;
  submissions_per_day: { day: string; count: number }[];
  most_solved: ProblemCount[];
  least_solved: ProblemCount[];
}

export interface RatingCorrection {
  scope: "global" | "tag" | "duel";
  tag?: string;
  rating: number;
  reason: string;
}

export interface AuditEntry {
  id: number;
  admin_id: number;
  admin_name: string;
  action: string;
  target_type: string;
  target_id: number | null;
  target_label: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditPage {
  items: AuditEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface DuelProblemState {
  problem_id: number;
  number: number;
  solved: boolean;
  best_score: number;
}

export interface DuelMatchState {
  id: number;
  remaining_seconds: number;
  ends_at: string;
  problems: DuelProblemState[];
  me: { solved: number; total: number };
  opponent: { solved: number; total: number; connected: boolean };
}

export interface DuelState {
  status: "idle" | "waiting" | "active";
  last_match_id: number | null;
  waiting?: { seconds: number };
  match?: DuelMatchState;
}

export interface DuelRatingView {
  rating: number;
  games: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface DuelHistoryItem {
  match_id: number;
  finished_at: string | null;
  result: "win" | "loss" | "draw";
  reason: string;
  rating_change: number | null;
}

export interface DuelPlayerResult {
  user_id: number;
  name: string;
  solved: number;
  total_score: number;
  penalty_minutes: number;
  failed_submissions: number;
  rating_before: number;
  rating_after: number | null;
  rating_change: number | null;
  problems: {
    problem_id: number;
    solved: boolean;
    best_score: number;
    failed_submissions: number;
    solved_minutes: number | null;
    penalty_minutes: number;
  }[];
}

export interface DuelResult {
  match_id: number;
  started_at: string;
  finished_at: string | null;
  winner_id: number | null;
  draw: boolean;
  reason: string;
  problems: { problem_id: number; number: number; title: string }[];
  players: DuelPlayerResult[];
}
