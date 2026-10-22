import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  type AnglePick,
  copyIssues,
  type CreativeDraft,
  type CreativeRow,
  creativeCount,
  draftCount,
  groupCreatives,
  isActive,
  LIMITS,
  lines,
  validatePicks,
  wordCount,
  worstPolicy,
} from "./ads";

const long = "x".repeat(300);

function draft(over: Partial<CreativeDraft> = {}, image: Partial<CreativeDraft["image"]> = {}): CreativeDraft {
  return {
    template_id: "headline_bold",
    variant_note: "",
    image: {
      headline: "Pedidos ordenados en una sola lista",
      subheadline: "Un método simple",
      kicker: "Método en 7 días",
      bullets: [],
      cta_text: "Quiero ordenarme",
      price_text: "",
      note: "",
      mark: "check",
      ...image,
    },
    ad: { primary_short: "Corto", primary_long: long, headline: "Ordena tus pedidos", description: "Método simple", cta: "LEARN_MORE" },
    scene: "",
    stock_keywords: [],
    proof_id: null,
    ...over,
  };
}

const keys = (d: CreativeDraft) => copyIssues(d).map((i) => i.key);

describe("copyIssues (mismas reglas que el backend)", () => {
  it("un borrador correcto no tiene avisos", () => {
    expect(copyIssues(draft())).toEqual([]);
  });

  it("avisa de textos demasiado largos con su medida", () => {
    const issues = copyIssues(
      draft({}, { headline: "uno dos tres cuatro cinco seis siete ocho nueve diez once", kicker: "a b c d e", cta_text: "a b c d e", note: "n".repeat(221) }),
    );
    expect(issues.map((i) => i.key)).toEqual(expect.arrayContaining(["imageHeadlineWords", "kickerWords", "ctaWords", "noteMax"]));
    expect(issues.find((i) => i.key === "imageHeadlineWords")?.values).toEqual({ n: 11, max: LIMITS.imageHeadlineWords });
  });

  it("exige titular y valida los largos de Ads Manager", () => {
    expect(keys(draft({}, { headline: "  " }))).toContain("headlineEmpty");
    const base = draft();
    const bad = { ...base, ad: { ...base.ad, primary_short: "p".repeat(126), headline: "h".repeat(41), description: "d".repeat(31), primary_long: "corto" } };
    expect(keys(bad)).toEqual(expect.arrayContaining(["primaryShortMax", "headlineMax", "descriptionMax", "primaryLongRange"]));
    expect(keys({ ...base, ad: { ...base.ad, primary_long: "x".repeat(701) } })).toContain("primaryLongRange");
    expect(keys({ ...base, ad: { ...base.ad, primary_long: "x".repeat(200) } })).not.toContain("primaryLongRange");
  });

  it("las listas exigen de 3 a 5 ítems y las comparaciones 2 o 4", () => {
    const items = (n: number) => Array.from({ length: n }, (_, i) => `ítem ${i}`);
    for (const template of ["checklist", "offer_stack"]) {
      expect(keys(draft({ template_id: template }, { bullets: items(2) }))).toContain("bulletsRange");
      expect(keys(draft({ template_id: template }, { bullets: items(3) }))).not.toContain("bulletsRange");
      expect(keys(draft({ template_id: template }, { bullets: items(6) }))).toContain("bulletsRange");
    }
    for (const template of ["before_after", "comparison"]) {
      expect(keys(draft({ template_id: template }, { bullets: items(3) }))).toContain("bulletsPaired");
      expect(keys(draft({ template_id: template }, { bullets: items(2) }))).not.toContain("bulletsPaired");
      expect(keys(draft({ template_id: template }, { bullets: items(4) }))).not.toContain("bulletsPaired");
    }
  });

  it("la plantilla de nota necesita su texto y un ítem largo se avisa", () => {
    expect(keys(draft({ template_id: "note" }, { note: " " }))).toContain("noteRequired");
    expect(keys(draft({ template_id: "note" }, { note: "Hola" }))).not.toContain("noteRequired");
    expect(keys(draft({ template_id: "checklist" }, { bullets: ["a b c d e f g h", "b", "c"] }))).toContain("bulletWords");
  });
});

describe("helpers de texto", () => {
  it("cuenta palabras ignorando espacios de más", () => {
    expect(wordCount("")).toBe(0);
    expect(wordCount("   ")).toBe(0);
    expect(wordCount(" uno   dos\ttres ")).toBe(3);
  });

  it("lines quita vacíos y espacios", () => {
    expect(lines(" a \n\n b\n  \nc ")).toEqual(["a", "b", "c"]);
    expect(lines("")).toEqual([]);
  });
});

const pick = (angle: string, avatar = "A", count = 2): AnglePick => ({ angle_id: angle, avatar, count });

describe("lote", () => {
  it("cuenta borradores (los paga la IA) e imágenes (una por formato)", () => {
    const picks = [pick("dolor", "A", 2), pick("mito", "B", 3)];
    expect(draftCount(picks)).toBe(5);
    expect(creativeCount(picks, ["4x5", "1x1", "9x16"])).toBe(15);
    expect(creativeCount(picks, [])).toBe(5); // sin formatos no se multiplica por cero
  });

  it("valida el tope de ángulos, de borradores y las repeticiones", () => {
    expect(validatePicks([pick("dolor"), pick("mito")])).toBe("none");
    expect(validatePicks(Array.from({ length: 9 }, (_, i) => pick(`a${i}`, "A", 1)))).toBe("tooMany");
    expect(validatePicks([pick("a", "A", 5), pick("b", "A", 5), pick("c", "A", 5), pick("d", "A", 5), pick("e", "A", 1)])).toBe("tooManyCreatives");
    expect(validatePicks([pick("dolor", "A"), pick("dolor", "A")])).toBe("duplicate");
    expect(validatePicks([pick("dolor", "A"), pick("dolor", "B")])).toBe("none"); // mismo ángulo, otro avatar
  });
});

function row(over: Partial<CreativeRow>): CreativeRow {
  return {
    id: "c",
    batch_id: "b",
    group_id: "g1",
    angle: "dolor",
    avatar: "A",
    template_id: "headline_bold",
    ratio: "4x5",
    copy: draft(),
    policy_status: "green",
    policy_notes: null,
    pre_score: 7,
    score_notes: null,
    status: "planned",
    version: 1,
    filename: "f.png",
    storage_path: null,
    image_provider: null,
    ...over,
  };
}

describe("groupCreatives", () => {
  it("agrupa los formatos de un borrador, los ordena y deja fuera los descartados", () => {
    const groups = groupCreatives([
      row({ id: "1", group_id: "g1", ratio: "1x1" }),
      row({ id: "2", group_id: "g1", ratio: "4x5" }),
      row({ id: "3", group_id: "g2", ratio: "9x16" }),
      row({ id: "4", group_id: "g3", status: "discarded" }),
    ]);
    expect(groups.map((g) => g.id)).toEqual(["g1", "g2"]);
    expect(groups[0].items.map((c) => c.ratio)).toEqual(["4x5", "1x1"]);
    expect(groups[0].lead.id).toBe("2");
  });

  it("un grupo con todos sus formatos descartados desaparece", () => {
    expect(groupCreatives([row({ status: "discarded" })])).toEqual([]);
  });
});

describe("semáforo y trabajos", () => {
  it("toma el peor semáforo", () => {
    expect(worstPolicy([row({ policy_status: "green" }), row({ policy_status: "red" }), row({ policy_status: "yellow" })])).toBe("red");
    expect(worstPolicy([row({ policy_status: "green" }), row({ policy_status: "yellow" })])).toBe("yellow");
    expect(worstPolicy([row({ policy_status: null })])).toBeNull();
  });

  it("un trabajo está activo si está en cola o corriendo", () => {
    expect(isActive(null)).toBe(false);
    expect(isActive({ status: "queued" })).toBe(true);
    expect(isActive({ status: "running" })).toBe(true);
    expect(isActive({ status: "done" })).toBe(false);
    expect(isActive({ status: "error" })).toBe(false);
  });
});

describe("textos es/pt", () => {
  const load = (name: string) => JSON.parse(readFileSync(`messages/${name}.json`, "utf8"));
  const flatten = (obj: unknown, prefix = ""): string[] =>
    obj && typeof obj === "object"
      ? Object.entries(obj).flatMap(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k))
      : [prefix];

  it("el módulo de anuncios tiene las mismas claves en español y portugués", () => {
    const es = flatten(load("es").ads).sort();
    const pt = flatten(load("pt").ads).sort();
    expect(pt).toEqual(es);
  });

  it("cada ángulo, plantilla y aviso del editor tiene su texto", () => {
    const { ads } = load("es");
    expect(Object.keys(ads.angleNames)).toHaveLength(14);
    expect(Object.keys(ads.templates)).toHaveLength(12);
    for (const key of ["headlineEmpty", "imageHeadlineWords", "primaryLongRange", "bulletsRange", "bulletsPaired", "noteRequired"]) {
      expect(ads.editor.issues[key]).toBeTruthy();
    }
  });
});
