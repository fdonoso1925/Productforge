// Espejo del módulo Creativos del backend (app/ads/schemas.py y app/ads/rules.py).
// El backend es la fuente de verdad: aquí solo se avisa antes de enviar y se agrupa para mostrar.

import type { Market } from "@/lib/types";

export const RATIOS = ["4x5", "9x16", "1x1"] as const;
export type Ratio = (typeof RATIOS)[number];

export const META_CTAS = ["LEARN_MORE", "SHOP_NOW", "GET_OFFER", "DOWNLOAD", "SIGN_UP"] as const;
export type MetaCta = (typeof META_CTAS)[number];

export type PolicyStatus = "green" | "yellow" | "red";

export type AdBrief = {
  market: Market;
  niche: string;
  product_name: string;
  problem: string;
  audience: string;
  promise: string;
  price_text: string;
  bonuses: string[];
  real_urgency: string;
};

export type Avatar = {
  name: string;
  situation: string;
  pain: string;
  desire: string;
  objections: string[];
  language: string[];
};

export type AngleInfo = { id: string; name: string; description: string; needs: string | null };
export type AngleSuggestion = { angle_id: string; avatar: string; why: string };
export type AnglePick = { angle_id: string; avatar: string; count: number };

export type ImageCopy = {
  headline: string;
  subheadline: string;
  kicker: string;
  bullets: string[];
  cta_text: string;
  price_text: string;
  note: string;
  mark: "check" | "cross";
};

export type AdCopy = {
  primary_short: string;
  primary_long: string;
  headline: string;
  description: string;
  cta: MetaCta;
};

export type CreativeDraft = {
  template_id: string;
  variant_note: string;
  image: ImageCopy;
  ad: AdCopy;
  scene: string;
  stock_keywords: string[];
  proof_id: string | null;
};

export type CreativeRow = {
  id: string;
  batch_id: string;
  group_id: string;
  angle: string;
  avatar: string;
  template_id: string;
  ratio: Ratio;
  copy: CreativeDraft;
  policy_status: PolicyStatus | null;
  policy_notes: { notes?: { rule: string; text: string }[]; rewrite?: string } | null;
  pre_score: number | null;
  score_notes: { explanation?: string; improvement?: string } | null;
  status: "planned" | "rendered" | "error" | "discarded";
  version: number;
  filename: string;
  storage_path: string | null;
  image_provider: string | null;
  parent_creative_id?: string | null;
  updated_at?: string;
};

export type BatchStatus = "planning" | "review" | "rendering" | "ready" | "error";

export type BatchDrive = {
  status?: "uploading" | "done" | "error";
  total?: number;
  uploaded?: number;
  failed?: number;
};

export type BatchRow = {
  id: string;
  product_id: string | null;
  niche: string;
  market: Market;
  template_id: string;
  brief: AdBrief;
  avatars: Avatar[];
  picks: AnglePick[];
  ratios: Ratio[];
  status: BatchStatus;
  drive: BatchDrive;
  parent_batch_id?: string | null;
  created_at: string;
};

export type AdJobRow = {
  id: string;
  kind: "ad_plan" | "ad_render" | "ad_drive" | "ad_iterate";
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: { stage?: string; done?: number; total?: number; failed?: number; angles_failed?: number };
  error: string | null;
};

export type Proof = {
  id: string;
  kind: "testimonial" | "stat" | "authority";
  text: string;
  author: string | null;
  product_id: string | null;
};

export type AdDrive = {
  connected: boolean;
  status: "none" | "uploading" | "done" | "error";
  total: number;
  uploaded: number;
  failed: number;
  folder_url: string | null;
};

// ───────────────────────────── límites (mismos valores que rules.py) ─────────────────────────────

export const LIMITS = {
  imageHeadlineWords: 10,
  imageSubWords: 14,
  kickerWords: 4,
  ctaWords: 4,
  bulletWords: 7,
  bullets: [3, 5] as const,
  noteMax: 220,
  primaryShortMax: 125,
  primaryLong: [200, 700] as const,
  headlineMax: 40,
  descriptionMax: 30,
  maxPicks: 8,
  maxCreativesPerBatch: 20,
  maxCount: 5,
} as const;

/** Plantillas cuyos bullets se muestran como lista y que, por tanto, los necesitan. */
export const LIST_TEMPLATES = ["checklist", "offer_stack"] as const;
export const PAIRED_TEMPLATES = ["before_after", "comparison"] as const;

export function wordCount(text: string): number {
  return text.trim() === "" ? 0 : text.trim().split(/\s+/).length;
}

export type Issue = { key: string; values?: Record<string, number | string> };

/** Avisos antes de guardar; el backend vuelve a validar todo con las mismas reglas. */
export function copyIssues(draft: CreativeDraft): Issue[] {
  const { image, ad } = draft;
  const out: Issue[] = [];
  const over = (key: string, n: number, max: number) => n > max && out.push({ key, values: { n, max } });
  if (image.headline.trim() === "") out.push({ key: "headlineEmpty" });
  over("imageHeadlineWords", wordCount(image.headline), LIMITS.imageHeadlineWords);
  over("imageSubWords", wordCount(image.subheadline), LIMITS.imageSubWords);
  over("kickerWords", wordCount(image.kicker), LIMITS.kickerWords);
  over("ctaWords", wordCount(image.cta_text), LIMITS.ctaWords);
  for (const bullet of image.bullets) over("bulletWords", wordCount(bullet), LIMITS.bulletWords);
  over("noteMax", image.note.length, LIMITS.noteMax);
  over("primaryShortMax", ad.primary_short.length, LIMITS.primaryShortMax);
  over("headlineMax", ad.headline.length, LIMITS.headlineMax);
  over("descriptionMax", ad.description.length, LIMITS.descriptionMax);
  const long = ad.primary_long.length;
  if (long < LIMITS.primaryLong[0] || long > LIMITS.primaryLong[1]) {
    out.push({ key: "primaryLongRange", values: { n: long, min: LIMITS.primaryLong[0], max: LIMITS.primaryLong[1] } });
  }
  const [lo, hi] = LIMITS.bullets;
  const bullets = image.bullets.length;
  if ((LIST_TEMPLATES as readonly string[]).includes(draft.template_id) && (bullets < lo || bullets > hi)) {
    out.push({ key: "bulletsRange", values: { n: bullets, min: lo, max: hi } });
  }
  if ((PAIRED_TEMPLATES as readonly string[]).includes(draft.template_id) && bullets !== 2 && bullets !== 4) {
    out.push({ key: "bulletsPaired", values: { n: bullets } });
  }
  if (draft.template_id === "note" && image.note.trim() === "") out.push({ key: "noteRequired" });
  return out;
}

// ───────────────────────────── lote ─────────────────────────────

export type PickIssue = "none" | "tooMany" | "tooManyCreatives" | "duplicate";

/** Cuántos creativos produce el lote: una imagen por borrador y formato. */
export function creativeCount(picks: AnglePick[], ratios: Ratio[]): number {
  return picks.reduce((n, p) => n + p.count, 0) * Math.max(ratios.length, 1);
}

/** Variaciones de copy que paga la IA (los formatos no cuestan: salen del mismo borrador). */
export function draftCount(picks: AnglePick[]): number {
  return picks.reduce((n, p) => n + p.count, 0);
}

export function validatePicks(picks: AnglePick[]): PickIssue {
  if (picks.length > LIMITS.maxPicks) return "tooMany";
  if (draftCount(picks) > LIMITS.maxCreativesPerBatch) return "tooManyCreatives";
  const keys = new Set(picks.map((p) => `${p.angle_id}|${p.avatar}`));
  if (keys.size !== picks.length) return "duplicate";
  return "none";
}

export type CreativeGroup = { id: string; items: CreativeRow[]; lead: CreativeRow };

/** Agrupa los formatos de un mismo borrador (comparten `group_id`); descarta los descartados. */
export function groupCreatives(rows: CreativeRow[]): CreativeGroup[] {
  const byGroup = new Map<string, CreativeRow[]>();
  for (const row of rows) {
    if (row.status === "discarded") continue;
    byGroup.set(row.group_id, [...(byGroup.get(row.group_id) ?? []), row]);
  }
  return [...byGroup.entries()].map(([id, items]) => {
    const sorted = [...items].sort((a, b) => RATIOS.indexOf(a.ratio) - RATIOS.indexOf(b.ratio));
    return { id, items: sorted, lead: sorted[0] };
  });
}

export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

/** Texto de búsqueda sin tildes ni mayúsculas, para filtrar listas en el navegador. */
export function normalizeSearch(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export const POLICY_ORDER: Record<PolicyStatus, number> = { green: 0, yellow: 1, red: 2 };

/** El peor semáforo de un grupo (todos sus formatos comparten texto, así que casi siempre es uno). */
export function worstPolicy(rows: CreativeRow[]): PolicyStatus | null {
  const found = rows.map((r) => r.policy_status).filter((s): s is PolicyStatus => s !== null);
  if (found.length === 0) return null;
  return found.reduce((a, b) => (POLICY_ORDER[b] > POLICY_ORDER[a] ? b : a));
}

export function isActive(job: Pick<AdJobRow, "status"> | null): boolean {
  return !!job && (job.status === "queued" || job.status === "running");
}

// ───────────────────────────── resultados y aprendizaje (fase 6) ─────────────────────────────

/** Con menos impresiones que esto, el CTR y el resto son ruido (igual que app/ads/learning.py). */
export const MIN_IMPRESSIONS = 1000;

export type ResultRow = {
  id: string;
  creative_id: string;
  day: string;
  spend: number;
  impressions: number;
  clicks: number;
  purchases: number;
  revenue: number;
  source: "manual" | "csv";
};

export type ResultInput = {
  day: string;
  spend: number;
  impressions: number;
  clicks: number;
  purchases: number;
  revenue: number;
};

export type Totals = Omit<ResultInput, "day">;

export type Derived = { ctr: number | null; cpc: number | null; cpa: number | null; roas: number | null };

export function sumResults(rows: Partial<Totals>[]): Totals {
  const total: Totals = { spend: 0, impressions: 0, clicks: 0, purchases: 0, revenue: 0 };
  for (const r of rows) {
    total.spend += Number(r.spend ?? 0);
    total.impressions += Number(r.impressions ?? 0);
    total.clicks += Number(r.clicks ?? 0);
    total.purchases += Number(r.purchases ?? 0);
    total.revenue += Number(r.revenue ?? 0);
  }
  return total;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/** CTR, CPC, CPA y ROAS salen de los TOTALES (nunca de promedios de promedios). */
export function derive(t: Totals): Derived {
  return {
    ctr: t.impressions ? round2((100 * t.clicks) / t.impressions) : null,
    cpc: t.clicks ? round2(t.spend / t.clicks) : null,
    cpa: t.purchases ? round2(t.spend / t.purchases) : null,
    roas: t.spend && t.revenue ? round2(t.revenue / t.spend) : null,
  };
}

export type ResultIssue = "future" | "clicksOverImpressions" | "purchasesWithoutClicks" | "negative" | "empty";

/** Mismas reglas que `ResultIn` del backend, para avisar antes de enviar. */
export function validateResult(input: ResultInput, today: string = new Date().toISOString().slice(0, 10)): ResultIssue[] {
  const out: ResultIssue[] = [];
  const nums = [input.spend, input.impressions, input.clicks, input.purchases, input.revenue];
  if (nums.some((n) => !Number.isFinite(n) || n < 0)) out.push("negative");
  if (!input.day) out.push("empty");
  else if (input.day > today) out.push("future");
  if (input.clicks > input.impressions) out.push("clicksOverImpressions");
  if (input.purchases > 0 && input.clicks === 0) out.push("purchasesWithoutClicks");
  return out;
}

export type InsightItem = Totals &
  Derived & {
    key: string;
    rank: number;
    winner: boolean;
    enough_data: boolean;
    // Solo en los hooks:
    creative_id?: string;
    headline?: string;
    ad_headline?: string;
    angle?: string;
    template_id?: string;
    filename?: string;
  };

export type InsightMetric = "roas" | "cpa" | "ctr" | "none";
export type InsightBlock = { metric: InsightMetric; items: InsightItem[] };

export type Insights = {
  totals: Totals & Derived;
  creatives_with_results: number;
  min_impressions: number;
  angles: InsightBlock;
  templates: InsightBlock;
  hooks: InsightBlock;
  winner_angles: string[];
};

export type ImageProviderStatus = {
  name: string;
  kind: "search" | "generate";
  enabled: boolean;
  free: boolean;
  requests_today: number;
  spent_today_usd: number;
  daily_cap_usd: number | null;
  exhausted: boolean;
};

export type ImportReport = {
  rows: number;
  matched: number;
  imported: number;
  unmatched: string[];
  ambiguous: string[];
  invalid: number;
  columns: string[];
};
