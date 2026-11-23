import { describe, expect, it } from "vitest";
import { canAddExtra, makeMain, toggleFormat } from "./formats";

describe("formatos del paquete (principal + extra)", () => {
  const base = { format: "pdf_guide", extraFormats: [] } as const;

  it("suma y quita formatos extra, y el principal no se quita", () => {
    const one = toggleFormat({ ...base, extraFormats: [] }, "mind_map");
    expect(one.extraFormats).toEqual(["mind_map"]);
    expect(toggleFormat(one, "mind_map").extraFormats).toEqual([]);
    expect(toggleFormat(one, "pdf_guide")).toEqual(one);
  });

  it("no deja pasar de 5 extra ni de 3 formatos pesados (solo caben como order bump)", () => {
    const heavy = { format: "pdf_guide" as const, extraFormats: ["sheet", "blueprint", "editable_template"] as const };
    expect(canAddExtra({ ...heavy, extraFormats: [...heavy.extraFormats] }, "epub")).toBe(false);
    expect(canAddExtra({ ...heavy, extraFormats: [...heavy.extraFormats] }, "planner")).toBe(true);
    const full = { format: "pdf_guide" as const, extraFormats: ["sheet", "planner", "checklist", "mind_map", "printable"] as const };
    expect(canAddExtra({ ...full, extraFormats: [...full.extraFormats] }, "swipe_file")).toBe(false);
  });

  it("hacer principal intercambia el principal con el extra", () => {
    const pick = makeMain({ format: "pdf_guide", extraFormats: ["mind_map", "planner"] }, "planner");
    expect(pick.format).toBe("planner");
    expect(pick.extraFormats).toEqual(["mind_map", "pdf_guide"]);
  });
});
