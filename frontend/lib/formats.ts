import {
  BookOpen,
  CalendarDays,
  Copy,
  FilePen,
  FileText,
  ListChecks,
  type LucideIcon,
  Map as MapIcon,
  Network,
  Printer,
  Share2,
  Sheet,
} from "lucide-react";
import { BONUS_FORMATS } from "@/lib/remodel";
import type { Format } from "@/lib/types";

export const FORMAT_ICONS: Record<Format, LucideIcon> = {
  pdf_guide: FileText,
  epub: BookOpen,
  mind_map: Network,
  concept_map: Share2,
  sheet: Sheet,
  checklist: ListChecks,
  blueprint: MapIcon,
  editable_template: FilePen,
  planner: CalendarDays,
  swipe_file: Copy,
  printable: Printer,
};

// ── Formatos del paquete: uno principal y, opcionalmente, otros que entran sí o sí ──
// (espejo de `PackageRequest.extra_formats` en el backend: el backend vuelve a validar).
export const MAX_EXTRA_FORMATS = 5; // 3 order bumps + 2 bonus
export const MAX_HEAVY_EXTRAS = 3; // los formatos no livianos solo caben como order bump

export type FormatPick = { format: Format; extraFormats: Format[] };

/** ¿Se puede sumar `format` a los extra sin pasarse de lo que cabe en el paquete? */
export function canAddExtra(pick: FormatPick, format: Format): boolean {
  if (format === pick.format || pick.extraFormats.includes(format))
    return false;
  if (pick.extraFormats.length >= MAX_EXTRA_FORMATS) return false;
  const heavy = pick.extraFormats.filter(
    (f) => !BONUS_FORMATS.includes(f),
  ).length;
  return BONUS_FORMATS.includes(format) || heavy < MAX_HEAVY_EXTRAS;
}

/** Tocar una tarjeta: suma o quita el formato de los extra. El principal no se quita (se cambia
 * con `makeMain`). Si no cabe, no cambia nada. */
export function toggleFormat(pick: FormatPick, format: Format): FormatPick {
  if (format === pick.format) return pick;
  if (pick.extraFormats.includes(format)) {
    return {
      ...pick,
      extraFormats: pick.extraFormats.filter((f) => f !== format),
    };
  }
  return canAddExtra(pick, format)
    ? { ...pick, extraFormats: [...pick.extraFormats, format] }
    : pick;
}

/** Convierte un formato en el principal; el principal anterior pasa a los extra si cabe. */
export function makeMain(pick: FormatPick, format: Format): FormatPick {
  if (format === pick.format) return pick;
  const rest = pick.extraFormats.filter((f) => f !== format);
  const next = { format, extraFormats: rest };
  return canAddExtra(next, pick.format)
    ? { format, extraFormats: [...rest, pick.format] }
    : next;
}
