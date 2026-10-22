import { env } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";
import type {
  ArtChoice,
  CoverSpec,
  DriveStatus,
  Format,
  Market,
  PackageOutline,
  Problem,
  ProductDrive,
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

export const api = {
  proposeProblems: (niche: string, market: Market) =>
    call<{ problems: Problem[] }>("/problems", {
      method: "POST",
      body: JSON.stringify({ niche, market }),
    }),
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
  downloadUrl: (fileId: string) => call<{ url: string }>(`/files/${fileId}/download`),
  templates: async (): Promise<TemplateInfo[]> => {
    const response = await fetch(`${env.apiUrl}/templates`);
    if (!response.ok) throw new ApiError(response.status, response.statusText);
    return response.json();
  },
  previewUrl: (templateId: string) => `${env.apiUrl}/templates/${templateId}/preview.png`,
};
