import { describe, expect, it } from "vitest";
import { checkPrice, defaultCurrency, forMarket, formatMoney, parseAmount, priceTexts, savingsPct } from "./price";

describe("precio de venta y precio normal", () => {
  it("lee cifras con coma o punto y formatea en reales o dólares", () => {
    expect(parseAmount("47")).toBe(47);
    expect(parseAmount("47,90")).toBe(47.9);
    expect(parseAmount("1.000")).toBe(1000);
    expect(parseAmount("1.299,90")).toBe(1299.9);
    expect(parseAmount("abc")).toBeNull();
    expect(formatMoney(47, "BRL")).toBe("R$ 47");
    expect(formatMoney(47.9, "BRL")).toBe("R$ 47,90");
    expect(formatMoney(1299.9, "USD")).toBe("US$ 1,299.90");
  });

  it("arma los textos solo con precios reales y válidos", () => {
    expect(priceTexts({ currency: "BRL", price: "47", base: "97" })).toEqual({ price_text: "R$ 47", base_price_text: "R$ 97" });
    expect(priceTexts({ currency: "USD", price: "", base: "49" })).toEqual({ price_text: "", base_price_text: "" });
    expect(priceTexts({ currency: "USD", price: "49", base: "19" }).base_price_text).toBe("");
    expect(savingsPct(97, 47)).toBe(52);
    expect(checkPrice({ currency: "BRL", price: "", base: "97" })).toBe("baseWithoutPrice");
    expect(checkPrice({ currency: "BRL", price: "97", base: "47" })).toBe("baseNotHigher");
    expect(checkPrice({ currency: "BRL", price: "x", base: "" })).toBe("invalid");
  });

  it("reales para Brasil y la moneda sigue al mercado hasta que se escribe un precio", () => {
    expect(defaultCurrency("pt-BR")).toBe("BRL");
    expect(defaultCurrency("es-LATAM")).toBe("USD");
    expect(forMarket({ currency: "USD", price: "", base: "" }, "pt-BR").currency).toBe("BRL");
    expect(forMarket({ currency: "USD", price: "19", base: "" }, "pt-BR").currency).toBe("USD");
  });
});
