import { describe, expect, it } from "vitest";
import { byProduct, crossWithAds, currenciesOf, dailySales, saleDay, type SaleRow, summarize } from "./hotmart";

const sale = (over: Partial<SaleRow>): SaleRow => ({
  transaction: "HP" + Math.random(),
  product_id: 1,
  product_name: "Guía",
  status: "APPROVED",
  order_date: "2026-10-01T10:00:00+00:00",
  approved_date: "2026-10-01T10:05:00+00:00",
  price: 50,
  currency: "USD",
  fee: 5,
  ...over,
});

describe("resumen de ventas", () => {
  const rows = [
    sale({}),
    sale({ price: 30, fee: 3 }),
    sale({ status: "COMPLETE", price: 20, fee: 2 }),
    sale({ status: "REFUNDED", price: 50 }),
    sale({ status: "WAITING_PAYMENT" }),
    sale({ status: "CANCELLED" }),
    sale({ status: "EXPIRED" }),
  ];

  it("separa pagadas, reembolsadas, pendientes y perdidas", () => {
    const s = summarize(rows);
    expect([s.paid, s.refunded, s.pending, s.lost]).toEqual([3, 1, 1, 2]);
  });

  it("calcula bruto, tarifa, neto y ticket solo con las pagadas", () => {
    const s = summarize(rows);
    expect(s.gross).toBe(100);
    expect(s.fees).toBe(10);
    expect(s.net).toBe(90);
    expect(s.avgTicket).toBe(33.33);
    expect(s.refundedAmount).toBe(50);
  });

  it("la tasa de reembolso se mide sobre las ventas que llegaron a pagarse", () => {
    expect(summarize(rows).refundRate).toBe(25); // 1 de 4
    expect(summarize([sale({ status: "CANCELLED" })]).refundRate).toBeNull();
    expect(summarize([]).avgTicket).toBeNull();
  });

  it("un contracargo cuenta como reembolso", () => {
    expect(summarize([sale({}), sale({ status: "CHARGEBACK" })]).refunded).toBe(1);
  });
});

describe("agrupaciones", () => {
  it("la venta cuenta el día de su aprobación y, si no, el del pedido", () => {
    expect(saleDay({ approved_date: "2026-10-02T01:00:00+00:00", order_date: "2026-10-01T23:00:00+00:00" })).toBe("2026-10-02");
    expect(saleDay({ approved_date: null, order_date: "2026-10-01T23:00:00+00:00" })).toBe("2026-10-01");
    expect(saleDay({ approved_date: null, order_date: null })).toBe("");
  });

  it("serie diaria: solo pagadas, en orden cronológico", () => {
    const series = dailySales([
      sale({ approved_date: "2026-10-03T00:00:00+00:00" }),
      sale({ approved_date: "2026-10-02T00:00:00+00:00", price: 10, fee: 1 }),
      sale({ approved_date: "2026-10-02T05:00:00+00:00", price: 10, fee: 1 }),
      sale({ status: "REFUNDED", approved_date: "2026-10-02T00:00:00+00:00" }),
    ]);
    expect(series).toEqual([
      { day: "2026-10-02", gross: 20, net: 18, sales: 2 },
      { day: "2026-10-03", gross: 50, net: 45, sales: 1 },
    ]);
  });

  it("nunca mezcla monedas: ordena por número de ventas", () => {
    expect(currenciesOf([sale({ currency: "BRL" }), sale({ currency: "USD" }), sale({ currency: "USD" })])).toEqual(["USD", "BRL"]);
  });

  it("agrupa por producto, el que más vendió primero", () => {
    const [first, second] = byProduct([
      sale({ product_id: 1, price: 10 }),
      sale({ product_id: 2, product_name: "Curso", price: 90 }),
    ]);
    expect([first.name, second.name]).toEqual(["Curso", "Guía"]);
  });
});

describe("cruce con anuncios", () => {
  const base = {
    links: [{ hotmart_product_id: 1, product_id: "p1" }],
    batches: [
      { id: "b1", product_id: "p1", meta: { currency: "USD" } },
      { id: "b2", product_id: "p1", meta: { currency: "MXN" } },
      { id: "b3", product_id: "p1", meta: null },
      { id: "b4", product_id: "otro", meta: { currency: "USD" } },
    ],
    creatives: [
      { id: "c1", batch_id: "b1" },
      { id: "c2", batch_id: "b2" },
      { id: "c4", batch_id: "b4" },
    ],
    spend: [
      { creative_id: "c1", day: "2026-10-02", spend: 20 },
      { creative_id: "c1", day: "2026-09-01", spend: 99 }, // fuera del período
      { creative_id: "c2", day: "2026-10-02", spend: 500 }, // otra moneda
      { creative_id: "c4", day: "2026-10-02", spend: 70 }, // producto no vinculado
    ],
    currency: "USD",
    since: "2026-10-01",
  };

  it("compara ventas de Hotmart con el gasto del mismo producto, moneda y período", () => {
    const { rows } = crossWithAds({ ...base, sales: [sale({}), sale({ price: 50, fee: 5 }), sale({ currency: "BRL" })] });
    expect(rows).toEqual([{ productId: 1, name: "Guía", gross: 100, net: 90, spend: 20, roas: 5, profit: 70 }]);
  });

  it("avisa de las campañas que no se pudieron incluir por su moneda", () => {
    expect(crossWithAds({ ...base, sales: [sale({})] }).excludedBatches).toBe(2);
  });

  it("sin gasto no hay ROAS", () => {
    const { rows } = crossWithAds({ ...base, spend: [], sales: [sale({})] });
    expect(rows[0].roas).toBeNull();
    expect(rows[0].profit).toBe(45);
  });
});
