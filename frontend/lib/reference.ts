import type { SalesReference } from "@/lib/types";

/** ¿Parece una dirección web? (el backend vuelve a validar todo; esto solo evita llamadas inútiles). */
export function looksLikeUrl(value: string): boolean {
  const text = value.trim();
  if (!text || /\s/.test(text)) return false;
  try {
    const url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`);
    return (url.protocol === "http:" || url.protocol === "https:") && url.hostname.includes(".");
  } catch {
    return false;
  }
}

/** Agrega https:// si la persona pegó solo «ejemplo.com/oferta». */
export function normalizeUrl(value: string): string {
  const text = value.trim();
  return /^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`;
}

/** El dominio de la referencia, para mostrarlo (sin ruta ni parámetros). */
export function referenceHost(reference: Pick<SalesReference, "source_url">): string | null {
  if (!reference.source_url) return null;
  try {
    return new URL(reference.source_url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Identifica una referencia para decidir si hay que pedir de nuevo problemas y estructura. */
export function referenceKey(reference: SalesReference | null | undefined): string {
  return reference ? JSON.stringify(reference) : "";
}

/** Largo máximo que acepta el backend para el pegado manual (caracteres). */
export const MAX_PASTED_TEXT = 30_000;
export const MIN_PASTED_TEXT = 400;
