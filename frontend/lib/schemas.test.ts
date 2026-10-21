import { describe, expect, it } from "vitest";
import { nicheSchema, outlineSchema, problemSchema } from "./schemas";

const item = (role: string, format: string) => ({
  role,
  format,
  title: "Título",
  promise: "Resultado en 7 días",
  objection_addressed: null,
  table_of_contents: ["Parte 1"],
  estimated_pages: 8,
  related_items: [],
});

describe("schemas", () => {
  it("limita el largo del nicho", () => {
    expect(nicheSchema.safeParse("Pets").success).toBe(true);
    expect(nicheSchema.safeParse("x".repeat(121)).success).toBe(false);
  });

  it("valida urgencia 1-5", () => {
    const problem = {
      title: "Salir del sobregiro",
      audience: "Asalariados",
      pain: "Intereses",
      promised_result: "Cuenta en cero",
      timeframe: "60 días",
      why_pay: "",
      urgency: 7,
    };
    expect(problemSchema.safeParse(problem).success).toBe(false);
  });

  it("acepta problemas con textos largos como los que genera la IA", () => {
    const problem = {
      title: "Sair do rotativo do cartão em 2 faturas",
      audience: "a".repeat(400),
      pain: "b".repeat(400),
      promised_result: "c".repeat(344),
      timeframe: "d".repeat(164),
      why_pay: "e".repeat(400),
      urgency: 5,
    };
    expect(problemSchema.safeParse(problem).success).toBe(true);
  });

  it("exige 3 order bumps y 2 bonus", () => {
    const outline = {
      product_name: "Paquete",
      main: item("main", "pdf_guide"),
      order_bumps: [item("order_bump", "sheet"), item("order_bump", "checklist")],
      bonuses: [item("bonus", "mind_map"), item("bonus", "planner")],
    };
    expect(outlineSchema.safeParse(outline).success).toBe(false);
    outline.order_bumps.push(item("order_bump", "swipe_file"));
    expect(outlineSchema.safeParse(outline).success).toBe(true);
  });

  it("acepta entradas de índice largas como las que genera la IA", () => {
    const main = { ...item("main", "pdf_guide"), table_of_contents: ["x".repeat(250)] };
    const outline = {
      product_name: "Paquete",
      main,
      order_bumps: [item("order_bump", "sheet"), item("order_bump", "checklist"), item("order_bump", "swipe_file")],
      bonuses: [item("bonus", "mind_map"), item("bonus", "planner")],
    };
    expect(outlineSchema.safeParse(outline).success).toBe(true);
  });
});
