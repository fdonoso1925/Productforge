import { describe, expect, it } from "vitest";
import { editableLeaves, flaggedPaths, isCheckoutUrl, previewDocument, sectionOf, setLeaf } from "./pages";

const content = {
  seo_title: "t",
  hero: { headline: "Promesa", bullets: ["a", "b", "c"] },
  faq: [{ q: "¿Cuándo?", a: "Hoy" }],
  offer: { title: "Oferta", price_text: "USD 12", guarantee: "7 días", urgency: "" },
  proof: { intro: "Lo que dicen", proof_ids: ["p1"] },
};

describe("editor de la página", () => {
  it("lista todos los textos con su ruta, sin lo que completa el sistema", () => {
    const paths = editableLeaves(content).map((l) => l.path);
    expect(paths).toEqual(["seo_title", "hero.headline", "hero.bullets.0", "hero.bullets.1", "hero.bullets.2", "faq.0.q", "faq.0.a", "offer.title", "proof.intro"]);
    expect(paths).not.toContain("offer.price_text");
    expect(paths).not.toContain("offer.guarantee");
  });

  it("cambia un texto anidado sin tocar el original", () => {
    const next = setLeaf(content, "faq.0.a", "Mañana") as typeof content;
    expect(next.faq[0].a).toBe("Mañana");
    expect(content.faq[0].a).toBe("Hoy");
    expect((setLeaf(content, "hero.bullets.1", "x") as typeof content).hero.bullets).toEqual(["a", "x", "c"]);
  });

  it("agrupa por sección y marca los textos parecidos a la página modelo", () => {
    expect(sectionOf("faq.0.a")).toBe("faq");
    const flagged = flaggedPaths({ level: "warn", ratio: 0.05, longest_run_words: 9, brands: [], fields: [{ path: "problem.intro", ratio: 0.3, run_words: 9 }] });
    expect(flagged.has("problem.intro")).toBe(true);
    expect(flaggedPaths(null).size).toBe(0);
  });
});

describe("enlace de compra", () => {
  it("solo acepta https completo y sin credenciales", () => {
    expect(isCheckoutUrl("https://pay.hotmart.com/X123")).toBe(true);
    for (const bad of ["http://x.com/p", "javascript:alert(1)", "https://localhost/p", "https://u:p@x.com/p", "pay.hotmart.com", ""]) {
      expect(isCheckoutUrl(bad)).toBe(false);
    }
  });
});

describe("vista previa", () => {
  it("abre los enlaces en otra pestaña", () => {
    expect(previewDocument("<html><head><title>x</title></head>")).toContain('<base target="_blank">');
  });
});
