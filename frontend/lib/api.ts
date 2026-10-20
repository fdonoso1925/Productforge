import { env } from "@/lib/env";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
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
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.json() as Promise<T>;
}
