import { describe, expect, it } from "vitest";
import { looksLikeUrl, normalizeUrl, referenceHost, referenceKey } from "./reference";
import type { SalesReference } from "./types";

const ref = (over: Partial<SalesReference> = {}): SalesReference => ({
  source_url: "https://www.ejemplo.com/oferta",
  niche_hint: "",
  product_name: "",
  audience: "",
  main_pain: "",
  pains: [],
  promise: "",
  benefits: [],
  objections: [],
  price_text: "",
  guarantee: "",
  bonuses: [],
  tone: "",
  angle: "",
  key_terms: [],
  ...over,
});

describe("looksLikeUrl", () => {
  it("acepta direcciones con o sin esquema", () => {
    for (const ok of ["https://ejemplo.com/oferta", "http://ejemplo.com", "ejemplo.com/oferta?x=1", "  www.ejemplo.com.br  "]) {
      expect(looksLikeUrl(ok)).toBe(true);
    }
  });

  it("rechaza lo que no es una dirección web", () => {
    for (const bad of ["", "   ", "hola mundo", "ftp://ejemplo.com", "javascript:alert(1)", "file:///etc/passwd", "localhost", "https://", "a b.com"]) {
      expect(looksLikeUrl(bad)).toBe(false);
    }
  });
});

describe("normalizeUrl", () => {
  it("agrega https solo cuando falta el esquema", () => {
    expect(normalizeUrl(" ejemplo.com/x ")).toBe("https://ejemplo.com/x");
    expect(normalizeUrl("http://ejemplo.com")).toBe("http://ejemplo.com");
  });
});

describe("referenceHost", () => {
  it("muestra el dominio sin www ni ruta", () => {
    expect(referenceHost(ref())).toBe("ejemplo.com");
    expect(referenceHost(ref({ source_url: null }))).toBeNull();
    expect(referenceHost(ref({ source_url: "no es url" }))).toBeNull();
  });
});

describe("referenceKey", () => {
  it("cambia cuando cambia la referencia y es vacío sin ella", () => {
    expect(referenceKey(null)).toBe("");
    expect(referenceKey(undefined)).toBe("");
    expect(referenceKey(ref())).not.toBe(referenceKey(ref({ main_pain: "otra" })));
    expect(referenceKey(ref())).toBe(referenceKey(ref()));
  });
});
