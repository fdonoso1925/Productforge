import { describe, expect, it } from "vitest";
import { checkCoverFile, coverOf, MAX_COVER_IMAGE_BYTES, sameCover } from "./cover";

describe("coverOf", () => {
  it("un producto anterior a las portadas queda sin arte", () => {
    expect(coverOf({ cover: {} })).toEqual({ art: "none", image_id: null, design: "template" });
  });

  it("respeta lo guardado", () => {
    expect(coverOf({ cover: { art: "topo", image_id: "abc" } })).toEqual({ art: "topo", image_id: "abc", design: "template" });
    expect(coverOf({ cover: { art: "auto", design: "editorial" } })).toEqual({ art: "auto", image_id: null, design: "editorial" });
  });
});

describe("sameCover", () => {
  it("compara estilo, imagen y diseño", () => {
    const base = { art: "topo", image_id: null, design: "template" } as const;
    expect(sameCover(base, { ...base })).toBe(true);
    expect(sameCover(base, { ...base, art: "waves" })).toBe(false);
    expect(sameCover(base, { ...base, image_id: "x" })).toBe(false);
    expect(sameCover(base, { ...base, design: "editorial" })).toBe(false);
  });
});

describe("checkCoverFile", () => {
  it("acepta JPG, PNG y WebP dentro del tope", () => {
    for (const type of ["image/jpeg", "image/png", "image/webp"]) {
      expect(checkCoverFile({ type, size: 1000 })).toBeNull();
    }
  });

  it("rechaza otros tipos y archivos muy grandes", () => {
    expect(checkCoverFile({ type: "image/gif", size: 1000 })).toBe("type");
    expect(checkCoverFile({ type: "application/pdf", size: 1000 })).toBe("type");
    expect(checkCoverFile({ type: "image/jpeg", size: MAX_COVER_IMAGE_BYTES + 1 })).toBe("size");
    expect(checkCoverFile({ type: "image/jpeg", size: MAX_COVER_IMAGE_BYTES })).toBeNull();
  });
});
