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
  dailySeries,
  derive,
  summarizeCampaigns,
  isActive,
  LIMITS,
  lines,
  normalizeSearch,
  sumResults,
  validateResult,
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
    scene: "Escritorio ordenado con una libreta",
    stock_keywords: ["desk", "notebook"],
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

  it("todo anuncio lleva foto de fondo: escena y 2 o 3 palabras clave", () => {
    expect(keys(draft({ scene: "  " }))).toContain("sceneRequired");
    expect(keys(draft({ stock_keywords: [] }))).toContain("keywordsRange");
    expect(keys(draft({ stock_keywords: ["solo"] }))).toContain("keywordsRange");
    expect(keys(draft({ stock_keywords: ["a", "b", "c", "d"] }))).toContain("keywordsRange");
    expect(keys(draft({ stock_keywords: ["a", "b", "c"] }))).not.toContain("keywordsRange");
    for (const template of ["headline_bold", "checklist", "note", "question", "photo_headline"]) {
      expect(keys(draft({ template_id: template, scene: "" }))).toContain("sceneRequired");
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

describe("resultados y métricas", () => {
  const day = "2026-03-04";

  it("suma los resultados y calcula CTR, CPC, CPA y ROAS de los totales", () => {
    const total = sumResults([
      { spend: 50, impressions: 4000, clicks: 80, purchases: 2, revenue: 150 },
      { spend: 50, impressions: 6000, clicks: 120, purchases: 3, revenue: 350 },
    ]);
    expect(total).toEqual({ spend: 100, impressions: 10000, clicks: 200, purchases: 5, revenue: 500 });
    expect(derive(total)).toEqual({ ctr: 2, cpc: 0.5, cpa: 20, roas: 5 });
  });

  it("sin datos no divide por cero", () => {
    expect(derive(sumResults([]))).toEqual({ ctr: null, cpc: null, cpa: null, roas: null });
    expect(derive({ spend: 10, impressions: 100, clicks: 0, purchases: 0, revenue: 0 })).toEqual({
      ctr: 0,
      cpc: null,
      cpa: null,
      roas: null,
    });
  });

  it("ignora campos ausentes al sumar", () => {
    expect(sumResults([{ spend: 5 }, { impressions: 10 }])).toEqual({ spend: 5, impressions: 10, clicks: 0, purchases: 0, revenue: 0 });
  });

  it("valida un resultado con las mismas reglas del backend", () => {
    const ok = { day, spend: 10, impressions: 1000, clicks: 20, purchases: 1, revenue: 30 };
    expect(validateResult(ok, "2026-03-05")).toEqual([]);
    expect(validateResult({ ...ok, day: "2026-03-06" }, "2026-03-05")).toContain("future");
    expect(validateResult({ ...ok, clicks: 2000 }, "2026-03-05")).toContain("clicksOverImpressions");
    expect(validateResult({ ...ok, clicks: 0 }, "2026-03-05")).toContain("purchasesWithoutClicks");
    expect(validateResult({ ...ok, spend: -1 }, "2026-03-05")).toContain("negative");
    expect(validateResult({ ...ok, spend: Number.NaN }, "2026-03-05")).toContain("negative");
    expect(validateResult({ ...ok, day: "" }, "2026-03-05")).toContain("empty");
    expect(validateResult({ ...ok, clicks: 0, purchases: 0 }, "2026-03-05")).toEqual([]);
  });

  it("la búsqueda ignora tildes y mayúsculas", () => {
    expect(normalizeSearch("  Bandeja ÚNICA ")).toBe("bandeja unica");
    expect(normalizeSearch("Produtividade")).toBe("produtividade");
  });
});

describe("dashboard de campañas", () => {
  const creatives = [
    { id: "c1", batch_id: "b1" },
    { id: "c2", batch_id: "b1" },
    { id: "c3", batch_id: "b2" },
  ];
  const row = (creative_id: string, day: string, spend: number, impressions: number, clicks: number, purchases = 0, revenue = 0) => ({
    creative_id,
    day,
    spend,
    impressions,
    clicks,
    purchases,
    revenue,
  });
  const results = [
    row("c1", "2026-10-01", 10, 1000, 20, 1, 30),
    row("c2", "2026-10-01", 5, 500, 5),
    row("c3", "2026-10-02", 40, 2000, 40, 2, 120),
    row("huerfano", "2026-10-02", 99, 1, 1),
  ];

  it("suma por campaña desde los totales y ordena por gasto", () => {
    const [first, second] = summarizeCampaigns(creatives, results);
    expect(first.batchId).toBe("b2");
    expect(first.derived.roas).toBe(3);
    expect(second.batchId).toBe("b1");
    expect(second.totals.spend).toBe(15);
    expect(second.derived.ctr).toBe(1.67); // 25 clics / 1500 impresiones, no el promedio de CTR
    expect(second.days).toBe(1);
  });

  it("agrupa gasto e ingresos por día en orden cronológico", () => {
    expect(dailySeries(results.slice(0, 3))).toEqual([
      { day: "2026-10-01", spend: 15, revenue: 30 },
      { day: "2026-10-02", spend: 40, revenue: 120 },
    ]);
  });
});
