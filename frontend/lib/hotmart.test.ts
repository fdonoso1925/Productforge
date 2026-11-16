import { describe, expect, it } from "vitest";
import {
  adsToUsd,
  byProduct,
  crossWithAds,
  currenciesOf,
  dailySales,
  inRange,
  ratesNeeded,
  saleDay,
  type SaleRow,
  salesToUsd,
  summarize,
} from "./hotmart";

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

describe("facturación neta real", () => {
  it("suma la comisión real de Hotmart y estima solo las ventas que aún no la tienen", () => {
    const s = summarize([
      sale({ price: 100, fee: 10, net_usd: 80 }), // real: 80 (no 90)
      sale({ price: 50, fee: 5, net_usd: 41.5 }),
      sale({ price: 30, fee: 3 }), // sin dato real: 27 estimado
    ]);
    expect(s.net).toBe(148.5);
    expect(s.netEstimated).toBe(1);
  });

  it("sin ningún dato real todo es estimación; el bruto no cambia", () => {
    const s = summarize([sale({ price: 100, fee: 10 })]);
    expect(s).toMatchObject({ gross: 100, net: 90, netEstimated: 1 });
  });

  it("la serie diaria también usa el neto real", () => {
    expect(dailySales([sale({ price: 100, fee: 10, net_usd: 80 })])[0].net).toBe(80);
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

  it("un rango de fechas deja fuera el gasto de después del último día", () => {
    const spend = [
      { creative_id: "c1", day: "2026-10-02", spend: 20 },
      { creative_id: "c1", day: "2026-10-20", spend: 30 }, // después del rango
    ];
    const { rows } = crossWithAds({ ...base, spend, until: "2026-10-10", sales: [sale({})] });
    expect(rows[0].spend).toBe(20);
  });
});

describe("conversión a USD", () => {
  const rates = {
    by_day: { "2026-10-01": { BRL: 5, COP: 4000 } },
    latest: { BRL: 5.5, COP: 3500, MXN: 20 },
  };

  it("convierte con el tipo de cambio del día y deja la comisión como viene (ya está en USD)", () => {
    const { rows, unconverted } = salesToUsd(
      [sale({ currency: "BRL", price: 100, fee: 3 }), sale({ currency: "COP", price: 400000, fee: 7 })],
      rates,
    );
    expect(unconverted).toBe(0);
    expect(rows.map((r) => [r.currency, r.price, r.fee])).toEqual([
      ["USD", 20, 3],
      ["USD", 100, 7],
    ]);
  });

  it("un día sin dato usa el último tipo de cambio y las ventas en USD no se tocan", () => {
    const { rows } = salesToUsd(
      [sale({ currency: "BRL", price: 110, approved_date: "2026-10-05T10:00:00Z" }), sale({ currency: "USD", price: 47 })],
      rates,
    );
    expect(rows.map((r) => r.price)).toEqual([20, 47]);
  });

  it("usa el tipo de cambio que aplicó Hotmart (y no pide uno de mercado) cuando la venta lo trae", () => {
    const hotmartRate = sale({ currency: "BRL", price: 119, fee: 2.49, net_usd: 17.64, payout_rate: 0.169174 });
    const { rows } = salesToUsd([hotmartRate], { by_day: {}, latest: {} }); // sin tipos de mercado
    expect(rows[0].price).toBe(20.13);
    expect(rows[0].price - rows[0].fee).toBeCloseTo(rows[0].net_usd as number, 2); // bruto y neto cuadran
    const needed = ratesNeeded({ sales: [hotmartRate], batches: [], creatives: [], spend: [] });
    expect(needed.currencies).toEqual([]);
  });

  it("sin tipo de cambio para la moneda, la venta se deja fuera y se cuenta", () => {
    const out = salesToUsd([sale({ currency: "CLP" }), sale({ currency: "USD" })], rates);
    expect(out.rows).toHaveLength(1);
    expect(out.unconverted).toBe(1);
  });

  it("pide tipos de cambio solo de los días y monedas que no son USD", () => {
    const needed = ratesNeeded({
      sales: [sale({ currency: "BRL" }), sale({ currency: "USD", approved_date: "2026-01-01T00:00:00Z" })],
      batches: [
        { id: "b1", product_id: "p", meta: { currency: "MXN" } },
        { id: "b2", product_id: "p", meta: { currency: "USD" } },
        { id: "b3", product_id: "p", meta: null },
      ],
      creatives: [
        { id: "c1", batch_id: "b1" },
        { id: "c2", batch_id: "b2" },
        { id: "c3", batch_id: "b3" },
      ],
      spend: [
        { creative_id: "c1", day: "2026-10-03", spend: 10 },
        { creative_id: "c2", day: "2026-10-04", spend: 10 },
        { creative_id: "c3", day: "2026-10-05", spend: 10 },
      ],
    });
    expect(needed.currencies).toEqual(["BRL", "MXN"]);
    expect(needed.days).toContain("2026-10-03");
    expect(needed.days).not.toContain("2026-10-04");
    expect(needed.days).not.toContain("2026-10-05");
    expect(needed.days).not.toContain("2026-01-01");
  });

  it("el gasto en otra moneda pasa a USD y la campaña entra al cruce; sin moneda sigue excluida", () => {
    const out = adsToUsd(
      {
        batches: [
          { id: "b1", product_id: "p1", meta: { currency: "MXN" } },
          { id: "b2", product_id: "p1", meta: null },
        ],
        creatives: [
          { id: "c1", batch_id: "b1" },
          { id: "c2", batch_id: "b2" },
        ],
        spend: [
          { creative_id: "c1", day: "2026-10-02", spend: 400 },
          { creative_id: "c2", day: "2026-10-02", spend: 70 },
        ],
      },
      rates,
    );
    expect(out.batches.map((b) => b.meta?.currency ?? null)).toEqual(["USD", null]);
    expect(out.spend.map((s) => s.spend)).toEqual([20, 70]);
  });
});

describe("rango de fechas (calendario)", () => {
  it("incluye el primer y el último día y respeta los límites vacíos", () => {
    expect(inRange("2026-01-10", "2026-01-10", "2026-03-20")).toBe(true);
    expect(inRange("2026-03-20", "2026-01-10", "2026-03-20")).toBe(true);
    expect(inRange("2026-01-09", "2026-01-10", "2026-03-20")).toBe(false);
    expect(inRange("2026-03-21", "2026-01-10", "2026-03-20")).toBe(false);
    expect(inRange("2020-01-01", "", "")).toBe(true);
    expect(inRange("2026-05-01", "2026-01-01")).toBe(true);
  });
});
