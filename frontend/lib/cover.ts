import type { ArtChoice, CoverSpec, ProductRow } from "@/lib/types";

export const MAX_COVER_IMAGE_BYTES = 5 * 1024 * 1024; // mismo tope que el backend
export const COVER_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const ART_CHOICES: ArtChoice[] = ["auto", "topo", "waves", "circles", "bauhaus", "facets", "none"];

/** La portada de un producto; uno anterior a las portadas (`cover: {}`) se ve sin arte. */
export function coverOf(product: Pick<ProductRow, "cover">): CoverSpec {
  return { art: product.cover?.art ?? "none", image_id: product.cover?.image_id ?? null };
}

export function sameCover(a: CoverSpec, b: CoverSpec): boolean {
  return a.art === b.art && a.image_id === b.image_id;
}

/** Valida el archivo antes de subirlo (el backend vuelve a validar todo). Devuelve la clave del error. */
export function checkCoverFile(file: Pick<File, "type" | "size">): "type" | "size" | null {
  if (!COVER_IMAGE_TYPES.includes(file.type)) return "type";
  if (file.size > MAX_COVER_IMAGE_BYTES) return "size";
  return null;
}
