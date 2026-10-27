// Espejo de los schemas Pydantic del backend (app/content/schemas).

export type Market = "pt-BR" | "es-LATAM";
export type Role = "main" | "order_bump" | "bonus";

export const FORMATS = [
  "pdf_guide",
  "epub",
  "mind_map",
  "concept_map",
  "sheet",
  "checklist",
  "blueprint",
  "editable_template",
  "planner",
  "swipe_file",
  "printable",
] as const;
export type Format = (typeof FORMATS)[number];

export type Problem = {
  title: string;
  audience: string;
  pain: string;
  promised_result: string;
  timeframe: string;
  why_pay: string;
  urgency: number;
};

export type ItemOutline = {
  role: Role;
  format: Format;
  title: string;
  promise: string;
  objection_addressed: string | null;
  table_of_contents: string[];
  estimated_pages: number;
  related_items: string[];
};

export type PackageOutline = {
  product_name: string;
  main: ItemOutline;
  order_bumps: ItemOutline[];
  bonuses: ItemOutline[];
};

export type CommercialSheet = {
  product_name: string;
  alternative_names: string[];
  headline: string;
  subheadline: string;
  currency: string;
  main_price: { min: number; max: number };
  order_bumps: { title: string; price: number; checkout_text: string }[];
  bonuses: { title: string; perceived_value: number }[];
  short_description: string;
  benefit_bullets: string[];
  ad_hooks: string[];
};

export type TemplateInfo = {
  id: string;
  name: string;
  description: string;
  palette: Record<string, string>;
  heading_font: string;
  body_font: string;
};

/** Estilos de arte generativo de la portada (los mismos del backend: app/generators/cover_art.py). */
export const ART_STYLES = ["topo", "waves", "circles", "bauhaus", "facets"] as const;
export type ArtStyle = (typeof ART_STYLES)[number];
export type ArtChoice = "auto" | ArtStyle | "none";
export type CoverSpec = { art: ArtChoice; image_id: string | null };

/** Resumen de una página de ventas que sirve de inspiración (espejo de SalesReference del backend). */
export type SalesReference = {
  source_url: string | null;
  niche_hint: string;
  product_name: string;
  audience: string;
  main_pain: string;
  pains: string[];
  promise: string;
  benefits: string[];
  objections: string[];
  price_text: string;
  guarantee: string;
  bonuses: string[];
  tone: string;
  angle: string;
  key_terms: string[];
};

export type ReferenceResult = {
  reference: SalesReference;
  page: { title: string; chars: number; truncated: boolean; source: "url" | "text" };
  looks_like_sales_page: boolean;
};

export type Niche = { id: string; slug: string; name: string; market: Market };

export type ProductRow = {
  id: string;
  title: string | null;
  niche: string;
  market: Market;
  main_format: Format;
  template_id: string;
  status: "draft" | "outline_ready" | "generating" | "ready" | "error";
  outline: PackageOutline | null;
  commercial: CommercialSheet | null;
  tone: string | null;
  audience_override: string | null;
  /** {} en los productos anteriores a las portadas (se ven sin arte). */
  cover: Partial<CoverSpec>;
  /** Página de ventas que inspiró el paquete (null si no hubo). */
  reference?: SalesReference | null;
  parent_product_id: string | null;
  root_product_id: string | null;
  created_at: string;
  updated_at: string;
};

/** Columnas que lista el historial (y el árbol de versiones). */
export type HistoryRow = Pick<
  ProductRow,
  "id" | "title" | "niche" | "market" | "main_format" | "template_id" | "status" | "parent_product_id" | "created_at"
>;

export type ItemRow = {
  id: string;
  role: Role;
  format: Format;
  title: string;
  status: "pending" | "generating" | "ready" | "error";
  order: number;
};

export type FileRow = {
  id: string;
  product_item_id: string | null;
  file_type: string;
  storage_path: string;
  size: number;
};

export type DriveStatus = { configured: boolean; connected: boolean; account: string | null };

export type ProductDrive = {
  connected: boolean;
  total: number;
  uploaded: number;
  pending: number;
  failed: number;
  syncing: boolean;
  folder_url: string | null;
};

export type JobRow = {
  id: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: {
    stage?: "adapting" | "items" | "commercial" | "zip" | "done";
    items?: Record<string, ItemRow["status"]>;
    done?: number;
    total?: number;
  };
  error: string | null;
  created_at: string;
};
