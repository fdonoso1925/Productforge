import type { Format, ItemRow } from "@/lib/types";

// Espejo de backend/app/pipeline/remodel.py (plan_remodel) y app/content/schemas/common.py
// (BONUS_FORMATS). Sirve para avisar cuánto usará IA un remodelado ANTES de crearlo; el
// servidor es quien decide de verdad, así que si cambian, hay que cambiar ambos.

/** Formatos livianos permitidos para un bonus. */
export const BONUS_FORMATS: Format[] = ["mind_map", "concept_map", "swipe_file", "planner", "pdf_guide", "checklist"];

// Formatos que comparten schema de contenido: cambiar entre ellos no necesita IA.
const SCHEMA_GROUP: Partial<Record<Format, string>> = { pdf_guide: "guide", epub: "guide" };

export function sameSchema(a: Format, b: Format): boolean {
  return a === b || (SCHEMA_GROUP[a] !== undefined && SCHEMA_GROUP[a] === SCHEMA_GROUP[b]);
}

export type RemodelPlan = { generate: number; rerender: number };

export function planRemodel(
  items: Pick<ItemRow, "id" | "format" | "status">[],
  formats: Record<string, Format>,
  contentChanged: boolean,
): RemodelPlan {
  const plan: RemodelPlan = { generate: 0, rerender: 0 };
  for (const item of items) {
    const next = formats[item.id];
    const needsAi =
      contentChanged ||
      item.status !== "ready" || // una pieza con error no tiene contenido que reutilizar
      (next !== undefined && next !== item.format && !sameSchema(item.format, next));
    plan[needsAi ? "generate" : "rerender"] += 1;
  }
  return plan;
}
