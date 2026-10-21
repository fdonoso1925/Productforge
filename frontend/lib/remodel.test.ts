import { describe, expect, it } from "vitest";
import { planRemodel, sameSchema } from "./remodel";
import type { Format } from "./types";

const item = (id: string, format: Format, status: "ready" | "error" = "ready") => ({ id, format, status });
const items = [item("m", "pdf_guide"), item("b", "sheet"), item("n", "mind_map")];

describe("planRemodel", () => {
  it("cambiar solo la plantilla no usa IA", () => {
    expect(planRemodel(items, {}, false)).toEqual({ generate: 0, rerender: 3 });
  });

  it("cambiar tono o público regenera todo", () => {
    expect(planRemodel(items, {}, true)).toEqual({ generate: 3, rerender: 0 });
  });

  it("guía PDF ↔ EPUB comparte schema: gratis; otro formato usa IA", () => {
    expect(planRemodel(items, { m: "epub" }, false)).toEqual({ generate: 0, rerender: 3 });
    expect(planRemodel(items, { m: "epub", b: "swipe_file" }, false)).toEqual({ generate: 1, rerender: 2 });
  });

  it("elegir el mismo formato que ya tiene no cuenta como cambio", () => {
    expect(planRemodel(items, { b: "sheet" }, false)).toEqual({ generate: 0, rerender: 3 });
  });

  it("una pieza con error se regenera aunque no cambie nada", () => {
    expect(planRemodel([item("m", "pdf_guide", "error"), item("b", "sheet")], {}, false)).toEqual({
      generate: 1,
      rerender: 1,
    });
  });
});

describe("sameSchema", () => {
  it("agrupa solo guía y EPUB", () => {
    expect(sameSchema("pdf_guide", "epub")).toBe(true);
    expect(sameSchema("sheet", "sheet")).toBe(true);
    expect(sameSchema("sheet", "checklist")).toBe(false);
  });
});
