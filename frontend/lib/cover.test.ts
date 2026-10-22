import { describe, expect, it } from "vitest";
import { checkCoverFile, coverOf, MAX_COVER_IMAGE_BYTES, sameCover } from "./cover";

describe("coverOf", () => {
  it("un producto anterior a las portadas queda sin arte", () => {
    expect(coverOf({ cover: {} })).toEqual({ art: "none", image_id: null });
  });

  it("respeta lo guardado", () => {
    expect(coverOf({ cover: { art: "topo", image_id: "abc" } })).toEqual({ art: "topo", image_id: "abc" });
    expect(coverOf({ cover: { art: "auto" } })).toEqual({ art: "auto", image_id: null });
  });
});

describe("sameCover", () => {
  it("compara estilo e imagen", () => {
    expect(sameCover({ art: "topo", image_id: null }, { art: "topo", image_id: null })).toBe(true);
    expect(sameCover({ art: "topo", image_id: null }, { art: "waves", image_id: null })).toBe(false);
    expect(sameCover({ art: "topo", image_id: null }, { art: "topo", image_id: "x" })).toBe(false);
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
