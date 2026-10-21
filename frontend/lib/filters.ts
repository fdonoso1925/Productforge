import type { Format, Market } from "@/lib/types";

export type HistoryFilters = {
  q: string;
  niche: string;
  market: "" | Market;
  format: "" | Format;
  from: string; // YYYY-MM-DD (fecha local)
  to: string; // YYYY-MM-DD, inclusive
};

export const EMPTY_FILTERS: HistoryFilters = { q: "", niche: "", market: "", format: "", from: "", to: "" };

export function hasFilters(f: HistoryFilters): boolean {
  return Object.values(f).some((v) => v !== "");
}

/**
 * Prepara el texto de búsqueda para el filtro `or(...)` de PostgREST. Esa sintaxis usa comas,
 * paréntesis y `*`/`%` como comodines; quitarlos evita que el usuario altere la consulta.
 */
export function sanitizeSearch(q: string): string {
  return q
    .replace(/[,()%*\\"'`:]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
}

function localDay(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Rango [gte, lt) en ISO para filtrar `created_at` por días locales, con `to` inclusivo. */
export function dateRange(from: string, to: string): { gte?: string; lt?: string } {
  const start = localDay(from);
  const end = localDay(to);
  if (end) end.setDate(end.getDate() + 1);
  return { gte: start?.toISOString(), lt: end?.toISOString() };
}
