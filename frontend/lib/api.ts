import { env } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";
import type {
  AdBrief,
  AdCopy,
  AdDrive,
  AngleInfo,
  AnglePick,
  AngleSuggestion,
  Avatar,
  CreativeRow,
  ImageCopy,
  ImageProviderStatus,
  ImportReport,
  Insights,
  MetaBatch,
  MetaPublishInput,
  MetaStatus,
  Proof,
  Ratio,
  ResultInput,
} from "@/lib/ads";
import type {
  PageBriefPreview,
  PageContent,
  PageInput,
  SimilarityReport,
  TeardownResult,
} from "@/lib/pages";
import type {
  ArtChoice,
  CoverSpec,
  DriveStatus,
  Format,
  Market,
  PackageOutline,
  Problem,
  ProductDrive,
  ReferenceResult,
  SalesReference,
  TemplateInfo,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public errors: string[] = [],
  ) {
    super(message);
  }
}

/** Llama al backend FastAPI con el JWT de Supabase. El frontend nunca llama a la IA. */
export async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${env.apiUrl}${path}`, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${token}`,
      // Solo el JSON lo fija aquí; un archivo (subida de imagen) lleva el tipo que le pase quien llama.
      ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    const errors: string[] = body?.errors ?? detail?.errors ?? [];
    throw new ApiError(response.status, typeof detail === "string" ? detail : response.statusText, errors);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function token(): Promise<string> {
  const { data } = await createClient().auth.getSession();
  const access = data.session?.access_token;
  if (!access) throw new ApiError(401, "sin sesión");
  return access;
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  return apiFetch<T>(path, await token(), init);
}

export type OutlineRequest = {
  niche: string;
  problem: Problem;
  market: Market;
  main_format: string;
  template_id: string;
  tone?: string | null;
  audience_override?: string | null;
  cover_art?: ArtChoice;
  reference?: SalesReference;
};

/** Solo viajan los campos que cambian: omitir `tone` lo conserva, `null` lo borra. */
export type RemodelBody = {
  template_id?: string;
  tone?: string | null;
  audience_override?: string | null;
  formats?: Record<string, Format>;
  /** Otra portada: solo cambia la maquetación (no usa IA). */
  cover?: CoverSpec;
};

/** O un producto existente (con precio y urgencia reales opcionales) o un brief manual. */
export type BriefSource = {
  product_id?: string;
  brief?: AdBrief;
  price_text?: string;
  real_urgency?: string;
};

export type BatchBody = BriefSource & {
  avatars: Avatar[];
  picks: AnglePick[];
  ratios: Ratio[];
  template_id?: string;
};

export type AdExport = { zip_url: string; csv_url: string; zip_name: string; images: number };

export const api = {
  proposeProblems: (niche: string, market: Market, reference?: SalesReference | null) =>
    call<{ problems: Problem[] }>("/problems", {
      method: "POST",
      body: JSON.stringify({ niche, market, ...(reference ? { reference } : {}) }),
    }),
  /** Lee una página de ventas (URL) o su texto pegado y la resume como inspiración. Usa IA. */
  analyzeReference: (body: { market: Market; url?: string; text?: string }) =>
    call<ReferenceResult>("/reference", { method: "POST", body: JSON.stringify(body) }),
  buildOutline: (body: OutlineRequest) =>
    call<{ product_id: string; outline: PackageOutline }>("/outline", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  saveOutline: (productId: string, outline: PackageOutline) =>
    call<PackageOutline>(`/products/${productId}/outline`, {
      method: "PUT",
      body: JSON.stringify(outline),
    }),
  generate: (productId: string) =>
    call<{ job_id: string }>(`/products/${productId}/generate`, { method: "POST" }),
  remodel: (productId: string, body: RemodelBody) =>
    call<{ product_id: string; job_id: string; plan: { generate: number; rerender: number } }>(
      `/products/${productId}/remodel`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  duplicate: (productId: string, market: Market) =>
    call<{ product_id: string; job_id: string }>(`/products/${productId}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ market }),
    }),
  regenerateItem: (productId: string, itemId: string) =>
    call<{ job_id: string }>(`/products/${productId}/items/${itemId}/regenerate`, { method: "POST" }),
  driveStatus: () => call<DriveStatus>("/storage/drive/status"),
  driveConnect: (locale: "es" | "pt") =>
    call<{ url: string }>("/storage/drive/connect", { method: "POST", body: JSON.stringify({ locale }) }),
  driveDisconnect: () => call<void>("/storage/drive", { method: "DELETE" }),
  driveSyncAll: () => call<{ products: number }>("/storage/drive/sync", { method: "POST" }),
  productDrive: (productId: string) => call<ProductDrive>(`/products/${productId}/drive`),
  productDriveSync: (productId: string) =>
    call<{ products: number }>(`/products/${productId}/drive/sync`, { method: "POST" }),
  setCover: (productId: string, cover: CoverSpec) =>
    call<CoverSpec>(`/products/${productId}/cover`, { method: "PUT", body: JSON.stringify(cover) }),
  /** El cuerpo es el archivo tal cual; el backend lo valida y lo guarda como JPEG limpio. */
  uploadCoverImage: (file: File) =>
    call<{ image_id: string; url: string; width: number; height: number }>("/cover-images", {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
    }),
  coverImageUrl: (imageId: string) => call<{ url: string }>(`/cover-images/${imageId}/url`),
  /** Muestra de un estilo con la paleta de la plantilla (SVG público). */
  artPreviewUrl: (style: string, templateId: string) =>
    `${env.apiUrl}/cover/art/${style}.svg?template=${encodeURIComponent(templateId)}&background=true`,
  // ── Creativos para Meta Ads ──
  adsBrief: (source: BriefSource) =>
    call<AdBrief>("/ads/brief", { method: "POST", body: JSON.stringify(source) }),
  adsAvatars: (source: BriefSource) =>
    call<{ brief: AdBrief; avatars: Avatar[] }>("/ads/avatars", {
      method: "POST",
      body: JSON.stringify(source),
    }),
  adsAngles: (source: BriefSource & { avatars: Avatar[]; count?: number }) =>
    call<{ available: AngleInfo[]; suggestions: AngleSuggestion[]; winners: string[] }>("/ads/angles", {
      method: "POST",
      body: JSON.stringify(source),
    }),
  adsCreateBatch: (body: BatchBody) =>
    call<{ batch_id: string; job_id: string }>("/ads/batches", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** `force` recompone también lo ya compuesto (p. ej. para ponerle foto de fondo a un lote anterior). */
  adsRender: (batchId: string, creativeIds: string[] = [], force = false) =>
    call<{ job_id: string }>(`/ads/batches/${batchId}/render`, {
      method: "POST",
      body: JSON.stringify({ creative_ids: creativeIds, force }),
    }),
  adsUrls: (batchId: string) => call<Record<string, string>>(`/ads/batches/${batchId}/urls`, { method: "POST" }),
  adsEdit: (
    creativeId: string,
    body: { image?: ImageCopy; ad?: AdCopy; stock_keywords?: string[]; scene?: string },
  ) =>
    call<CreativeRow>(`/ads/creatives/${creativeId}`, { method: "PUT", body: JSON.stringify(body) }),
  adsRenderOne: (creativeId: string) =>
    call<CreativeRow>(`/ads/creatives/${creativeId}/render`, { method: "POST" }),
  adsDiscard: (creativeId: string) =>
    call<CreativeRow>(`/ads/creatives/${creativeId}/discard`, { method: "POST" }),
  adsExport: (batchId: string) => call<AdExport>(`/ads/batches/${batchId}/export`, { method: "POST" }),
  adsDrive: (batchId: string) => call<AdDrive>(`/ads/batches/${batchId}/drive`),
  adsDriveStart: (batchId: string) =>
    call<{ job_id: string }>(`/ads/batches/${batchId}/drive`, { method: "POST" }),
  pagesReference: (body: { market: Market; url?: string; text?: string }) =>
    call<TeardownResult>("/pages/reference", { method: "POST", body: JSON.stringify(body) }),
  pagesBrief: (productId: string) => call<PageBriefPreview>(`/pages/brief?product_id=${productId}`),
  pagesCreate: (body: PageInput) =>
    call<{ page_id: string; job_id: string }>("/pages", { method: "POST", body: JSON.stringify(body) }),
  pagesState: (pageId: string) => call<{ working: boolean }>(`/pages/${pageId}/state`),
  pagesHtml: (pageId: string) => call<{ html: string; filename: string }>(`/pages/${pageId}/html`),
  pagesExport: (pageId: string) =>
    call<{ html: string; filename: string }>(`/pages/${pageId}/export`, { method: "POST" }),
  pagesLovable: (pageId: string) =>
    call<{ prompt: string; chars: number; link_ok: boolean }>(`/pages/${pageId}/lovable`),
  pagesEdit: (pageId: string, body: { content?: PageContent; checkout_url?: string; template_id?: string }) =>
    call<{ similarity: SimilarityReport }>(`/pages/${pageId}`, { method: "PUT", body: JSON.stringify(body) }),
  pagesRegenerate: (pageId: string) => call<{ job_id: string }>(`/pages/${pageId}/regenerate`, { method: "POST" }),
  pagesDelete: (pageId: string) => call<void>(`/pages/${pageId}`, { method: "DELETE" }),
  hotmartStatus: () =>
    call<{ configured: boolean; synced_at: string | null; last_error: string | null; count: number }>("/hotmart/status"),
  hotmartSync: (days = 90) =>
    call<{ sales: number }>("/hotmart/sync", { method: "POST", body: JSON.stringify({ days }) }),
  hotmartLink: (hotmartProductId: number, productId: string | null) =>
    call<void>(`/hotmart/products/${hotmartProductId}/link`, {
      method: "PUT",
      body: JSON.stringify({ product_id: productId }),
    }),
  adsMetaStatus: () => call<MetaStatus>("/ads/meta/status"),
  adsMeta: (batchId: string) => call<MetaBatch>(`/ads/batches/${batchId}/meta`),
  adsMetaPublish: (batchId: string, body: MetaPublishInput) =>
    call<{ job_id: string }>(`/ads/batches/${batchId}/meta`, { method: "POST", body: JSON.stringify(body) }),
  adsMetaSync: (batchId: string) =>
    call<{ job_id: string }>(`/ads/batches/${batchId}/meta/sync`, { method: "POST" }),
  adsSaveResult: (creativeId: string, body: ResultInput) =>
    call<{ saved: boolean }>(`/ads/creatives/${creativeId}/results`, { method: "PUT", body: JSON.stringify(body) }),
  adsDeleteResult: (resultId: string) => call<void>(`/ads/results/${resultId}`, { method: "DELETE" }),
  /** El cuerpo es el CSV de Ads Manager tal cual; el backend lo lee y lo empareja por nombre de archivo. */
  adsImportResults: (file: File) =>
    call<ImportReport>("/ads/results/import", {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.type || "text/csv" },
    }),
  adsInsights: (filters: { market?: Market; niche?: string } = {}) => {
    const query = new URLSearchParams();
    if (filters.market) query.set("market", filters.market);
    if (filters.niche) query.set("niche", filters.niche);
    return call<Insights>(`/ads/insights${query.size ? `?${query}` : ""}`);
  },
  /** Hooks nuevos para un creativo ya probado. Usa IA. */
  adsIterate: (creativeId: string, count = 2) =>
    call<{ job_id: string }>(`/ads/creatives/${creativeId}/iterate`, {
      method: "POST",
      body: JSON.stringify({ count }),
    }),
  /** Otra plantilla o formato con el mismo texto. No usa IA. */
  adsVariant: (creativeId: string, body: { template_id?: string; ratio?: Ratio }) =>
    call<CreativeRow>(`/ads/creatives/${creativeId}/variant`, { method: "POST", body: JSON.stringify(body) }),
  /** Adapta el lote al otro mercado y lo planifica de nuevo. Usa IA. */
  adsDuplicate: (batchId: string, market: Market) =>
    call<{ batch_id: string; job_id: string }>(`/ads/batches/${batchId}/duplicate`, {
      method: "POST",
      body: JSON.stringify({ market }),
    }),
  adsImagesStatus: () =>
    call<{ providers: ImageProviderStatus[]; photo_templates: boolean }>("/ads/images/status"),
  adsTemplates: () =>
    call<{ templates: { id: string; uses_image: boolean }[]; ratios: { id: Ratio }[] }>("/ads/templates"),
  adsProofs: (productId?: string) =>
    call<Proof[]>(`/ads/proofs${productId ? `?product_id=${productId}` : ""}`),
  adsAddProof: (body: { kind: Proof["kind"]; text: string; author?: string | null; product_id?: string | null }) =>
    call<Proof>("/ads/proofs", { method: "POST", body: JSON.stringify(body) }),
  adsDeleteProof: (proofId: string) => call<void>(`/ads/proofs/${proofId}`, { method: "DELETE" }),
  downloadUrl: (fileId: string) => call<{ url: string }>(`/files/${fileId}/download`),
  templates: async (): Promise<TemplateInfo[]> => {
    const response = await fetch(`${env.apiUrl}/templates`);
    if (!response.ok) throw new ApiError(response.status, response.statusText);
    return response.json();
  },
  previewUrl: (templateId: string) => `${env.apiUrl}/templates/${templateId}/preview.png`,
};
