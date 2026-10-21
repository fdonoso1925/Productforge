import { describe, expect, it } from "vitest";
import { dateRange, EMPTY_FILTERS, hasFilters, sanitizeSearch } from "./filters";

describe("sanitizeSearch", () => {
  it("quita los caracteres que alteran el filtro de PostgREST", () => {
    expect(sanitizeSearch("a,b),title.eq.x(%*")).toBe("a b title.eq.x");
    expect(sanitizeSearch(`  "x" 'y'  \\ `)).toBe("x y");
  });

  it("limita el largo y deja pasar texto normal con acentos", () => {
    expect(sanitizeSearch("Finanças pessoais")).toBe("Finanças pessoais");
    expect(sanitizeSearch("a".repeat(200))).toHaveLength(80);
  });

  it("devuelve vacío si solo había caracteres peligrosos", () => {
    expect(sanitizeSearch(",,()**")).toBe("");
  });
});

describe("dateRange", () => {
  it("'hasta' es inclusivo: el límite superior es el día siguiente", () => {
    const { gte, lt } = dateRange("2026-10-20", "2026-10-20");
    expect(gte && lt).toBeTruthy();
    const hours = (new Date(lt!).getTime() - new Date(gte!).getTime()) / 36e5;
    expect(hours).toBeGreaterThanOrEqual(23); // 23-25 h según cambios de horario
    expect(hours).toBeLessThanOrEqual(25);
  });

  it("ignora fechas vacías o inválidas", () => {
    expect(dateRange("", "")).toEqual({ gte: undefined, lt: undefined });
    expect(dateRange("20/10/2026", "no")).toEqual({ gte: undefined, lt: undefined });
  });

  it("puede filtrar solo por un extremo", () => {
    expect(dateRange("2026-10-01", "").lt).toBeUndefined();
    expect(dateRange("", "2026-10-01").gte).toBeUndefined();
  });
});

describe("hasFilters", () => {
  it("detecta si hay algún filtro activo", () => {
    expect(hasFilters(EMPTY_FILTERS)).toBe(false);
    expect(hasFilters({ ...EMPTY_FILTERS, market: "pt-BR" })).toBe(true);
  });
});
