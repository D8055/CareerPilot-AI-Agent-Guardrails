export type Role = "owner" | "viewer";

export interface Job {
  id: number | string;
  url: string;
  company: string;
  role: string;
  ats: string | null;
  channel: string | null;
  status: string;
  match: number | null;
  missing_keywords: string[];
  added_at: string;
}

export interface StatusEvent {
  status: string;
  note: string | null;
  ts: string;
}

export interface PlanMeta {
  id: number | string;
  created_by: string;
  quality_pass: boolean | string | null;
  summary_text: string;
  created_at: string;
}

export interface JobDetail extends Job {
  jd_text: string | null;
  status_events: StatusEvent[];
  plans: PlanMeta[];
  matched_keywords?: string[];
}

export interface TailorResult {
  match_score: number;
  matched_keywords: string[];
  missing_keywords: string[];
  plan: unknown;
  quality_pass: boolean | string | null;
}

export interface PlanFull {
  plan: {
    summary_text: string;
    skills: unknown;
    experience: unknown;
    projects: unknown;
  };
  created_by: string;
  quality_pass: boolean | string | null;
  honesty_report: unknown;
}

export interface CareerItem {
  id: number | string;
  ref: string;
  kind: string;
  section: string;
  text: string;
  tier: string | number;
  source?: string; // pool | owner
}

export interface RagHit {
  id?: number;
  ref: string;
  kind: string;
  section: string;
  text: string;
  score: number;
}

export interface TailoredResume {
  job_id: number;
  plan_id: number;
  created_by: string;
  quality_pass: string | boolean | null;
  resume: {
    contact: {
      name: string;
      location?: string;
      phone?: string;
      email?: string;
      linkedin?: string;
      work_authorization?: string;
    };
    summary: string;
    skills: { label: string; items: string[] }[];
    experience: { org: string; title: string; dates: string; bullets: string[] }[];
    projects: { name: string; stack: string; bullets: string[] }[];
    accomplishments: string[];
  };
}

export interface ResumeMeta {
  uploaded: boolean;
  id?: number;
  filename?: string;
  content_type?: string;
  size?: number;
  ts?: string;
}

export interface Question {
  id: number | string;
  question?: string;
  text?: string;
  job_id?: number | string | null;
  answer?: string | null;
  status?: string;
  created_at?: string;
  kind?: "keyword" | "form";
}

export interface AttentionItem {
  type: "quality_failed" | "enrich_failed";
  intelligence_id?: number | string;
  job_id: number | string;
  company: string;
  detail: string;
}

export interface Attention {
  counts: {
    open_questions: number;
    failed_items: number;
    quality_pending: number;
    runner_online: boolean;
  };
  items: AttentionItem[];
}

export interface AnswerEntry {
  id: number | string;
  pattern: string | null;
  question: string | null;
  answer: string;
  source: "learned" | "manual";
  uses: number;
}

export interface EvalRun {
  id: number | string;
  matrix_key: string;
  metrics: Record<string, number | string | null>;
  ts: string;
}

export type BlockerStatus = "waiting_on_dhiren" | "resolved" | "deferred";

export interface Blocker {
  code: string;
  title: string;
  detail: string;
  phase: string;
  status: BlockerStatus;
}

export interface Runner {
  id: number | string;
  hostname: string;
  last_heartbeat: string;
  online: boolean;
}

export interface Stats {
  jobs_total: number;
  by_status: Record<string, number>;
  plans: number;
  open_questions: number;
  quality_passes_pending: number;
  waiting_on_dhiren: number;
}
