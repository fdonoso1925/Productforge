import { env } from "@/lib/env";
import { createClient } from "@/lib/supabase/client";
import type { Market, PackageOutline, Problem, TemplateInfo } from "@/lib/types";

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
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail;
    const errors: string[] = body?.errors ?? detail?.errors ?? [];
    throw new ApiError(response.status, typeof detail === "string" ? detail : response.statusText, errors);
  }
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
  downloadUrl: (fileId: string) => call<{ url: string }>(`/files/${fileId}/download`),
  templates: async (): Promise<TemplateInfo[]> => {
    const response = await fetch(`${env.apiUrl}/templates`);
    if (!response.ok) throw new ApiError(response.status, response.statusText);
    return response.json();
  },
  previewUrl: (templateId: string) => `${env.apiUrl}/templates/${templateId}/preview.png`,
};
