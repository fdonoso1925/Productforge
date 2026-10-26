/** Páginas de ventas: tipos (espejo de `app/pages/schemas.py`) y ayudas de edición. */

import type { Market } from "@/lib/types";

export type PageStatus = "planning" | "ready" | "error";
export type SimilarityLevel = "ok" | "warn" | "block";

export type SimilarityReport = {
  level: SimilarityLevel;
  ratio: number;
  longest_run_words: number;
  fields: { path: string; ratio: number; run_words: number }[];
  brands: string[];
};

export type DeliverableKind = "main" | "bonus" | "bump";

export type PageBrief = {
  market: Market;
  niche: string;
  product_name: string;
  problem: string;
  audience: string;
  pain: string;
  promise: string;
  timeframe: string;
  why_pay: string;
  deliverables: { kind: DeliverableKind; title: string; promise: string; format: string; contents: string[] }[];
  price_text: string;
  guarantee_text: string;
  real_urgency: string;
  about_author: string;
  tone: string;
};

export type PageProof = { id: string; kind: "testimonial" | "stat" | "authority"; text: string; author: string | null };

export type PageReference = {
  source_url: string | null;
  brand_terms: string[];
  audience: string;
  main_pain: string;
  promise: string;
  structure: { kind: string; purpose: string }[];
  offer_summary: string;
  proof_types: string[];
  persuasion: string[];
  tone: string;
  angle: string;
  strengths: string[];
  weaknesses: string[];
  missing: string[];
  key_terms: string[];
};

export type TeardownResult = {
  reference: PageReference;
  fingerprint: string;
  page: { title: string; chars: number; truncated: boolean; source: "url" | "text" };
  looks_like_sales_page: boolean;
};

/** El contenido se edita como árbol de textos: la forma exacta la define el backend. */
export type PageContent = Record<string, unknown>;

export type PageRow = {
  id: string;
  product_id: string | null;
  market: Market;
  template_id: string;
  title: string;
  status: PageStatus;
  brief: PageBrief;
  reference: PageReference | null;
  content: PageContent | null;
  proofs: PageProof[];
  checkout_url: string | null;
  similarity: SimilarityReport | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type PageBriefPreview = { brief: PageBrief; template_id: string; proofs: PageProof[] };

export type PageInput = {
  market: Market;
  product_id?: string;
  manual?: {
    niche: string;
    product_name: string;
    problem: string;
    audience: string;
    promise: string;
    timeframe?: string;
  };
  template_id?: string;
  checkout_url?: string;
  price_text: string;
  guarantee_text: string;
  real_urgency: string;
  about_author: string;
  proof_ids: string[];
  reference?: PageReference;
  fingerprint?: string;
};

/** Mismo criterio que el backend: https con dominio y sin usuario ni clave. */
export function isCheckoutUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" && url.hostname.includes(".") && !url.username && !url.password;
  } catch {
    return false;
  }
}

/** Lo que el sistema completa solo (precio, garantía y urgencia salen de lo que dio el usuario). */
const READ_ONLY = new Set(["offer.price_text", "offer.guarantee", "offer.urgency", "proof.proof_ids"]);

export type TextLeaf = { path: string; value: string; multiline: boolean };

/** Todos los textos editables de la página, con su ruta (`hero.headline`, `faq.2.a`…). */
export function editableLeaves(content: PageContent): TextLeaf[] {
  const out: TextLeaf[] = [];
  const walk = (value: unknown, path: string) => {
    if (typeof value === "string") {
      if (![...READ_ONLY].some((r) => path === r || path.startsWith(`${r}.`))) out.push({ path, value, multiline: value.length > 90 || path.endsWith("intro") });
    } else if (Array.isArray(value)) value.forEach((v, i) => walk(v, path ? `${path}.${i}` : String(i)));
    else if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value)) walk(v, path ? `${path}.${k}` : k);
    }
  };
  walk(content, "");
  return out;
}

/** Devuelve una copia del contenido con el texto de `path` cambiado. */
export function setLeaf(content: PageContent, path: string, value: string): PageContent {
  const copy = structuredClone(content) as Record<string, unknown>;
  const keys = path.split(".");
  let node: unknown = copy;
  for (const key of keys.slice(0, -1)) node = (node as Record<string, unknown>)[key];
  (node as Record<string, unknown>)[keys[keys.length - 1]] = value;
  return copy;
}

/** Primer segmento de la ruta: la sección a la que pertenece un texto. */
export function sectionOf(path: string): string {
  return path.split(".")[0];
}

/** Rutas que el detector marcó como parecidas a la página modelo. */
export function flaggedPaths(report: SimilarityReport | null): Set<string> {
  return new Set((report?.fields ?? []).map((f) => f.path));
}

/** Vista previa: los enlaces se abren en otra pestaña en vez de cargar la compra dentro del marco. */
export function previewDocument(html: string): string {
  return html.replace("<head>", '<head><base target="_blank">');
}
