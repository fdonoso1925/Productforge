/** Métricas de Hotmart. Las ventas se leen de la API (solo lectura) y se resumen aquí. */

export type SaleRow = {
  transaction: string;
  product_id: number | null;
  product_name: string | null;
  status: string;
  order_date: string | null;
  approved_date: string | null;
  price: number;
  currency: string;
  /** Tarifa de Hotmart, siempre en USD. */
  fee: number;
  /** Facturación neta real: lo que Hotmart le paga al usuario por esta venta, en USD. */
  net_usd?: number | null;
  /** USD por 1 unidad de `currency` con el tipo de cambio que aplicó Hotmart. */
  payout_rate?: number | null;
};

export const PAID = new Set(["APPROVED", "COMPLETE", "PARTIALLY_REFUNDED"]);
export const REFUNDED = new Set(["REFUNDED", "CHARGEBACK"]);
export const PENDING = new Set(["STARTED", "WAITING_PAYMENT", "PRINTED_BILLET", "PROCESSING_TRANSACTION", "UNDER_ANALISYS", "PRE_ORDER"]);
// Todo lo demás (cancelada, vencida, sin fondos, bloqueada…) cuenta como venta perdida.

export type SalesSummary = {
  paid: number;
  refunded: number;
  pending: number;
  lost: number;
  gross: number;
  fees: number;
  /** Facturación neta real (con estimación solo en las ventas que aún no tienen el dato real). */
  net: number;
  /** Ventas pagadas cuyo neto es una estimación porque falta el dato real de Hotmart. */
  netEstimated: number;
  refundedAmount: number;
  /** Reembolsos y contracargos sobre las ventas que llegaron a pagarse, en %. */
  refundRate: number | null;
  avgTicket: number | null;
};

const round2 = (n: number) => Math.round(n * 100) / 100;

/** La venta cuenta el día en que se aprobó; si aún no, el día del pedido. */
export function saleDay(r: Pick<SaleRow, "approved_date" | "order_date">): string {
  return (r.approved_date ?? r.order_date ?? "").slice(0, 10);
}

/** Tipos de cambio del backend: unidades de cada moneda por 1 USD, por día y el último conocido. */
export type Rates = { by_day: Record<string, Record<string, number>>; latest: Record<string, number> };

/**
 * USD por 1 unidad de `currency` ese día. Sin dato del día se usa el último tipo de cambio
 * conocido; nulo si no hay ninguno (la venta no se puede pasar a dólares).
 */
export function usdFactor(rates: Rates, day: string, currency: string): number | null {
  if (currency === "USD") return 1;
  const perUsd = rates.by_day[day]?.[currency] ?? rates.latest[currency];
  return perUsd && perUsd > 0 ? 1 / perUsd : null;
}

/** ¿Tiene la venta el tipo de cambio que aplicó Hotmart? Entonces no hace falta uno de mercado. */
const hasPayoutRate = (r: SaleRow) => typeof r.payout_rate === "number" && r.payout_rate > 0;

/**
 * Todas las ventas en USD. Se usa el tipo de cambio que aplicó Hotmart al pagarlas (así el bruto
 * y el neto real cuadran: precio × tipo de cambio − tarifa = neto) y, si una venta aún no lo
 * tiene, el de mercado de su día. La comisión de Hotmart ya viene en USD (aunque la venta sea en
 * BRL o COP), así que no se toca. `unconverted` cuenta las ventas sin ningún tipo de cambio: se
 * dejan fuera en vez de mezclarlas.
 */
export function salesToUsd(rows: SaleRow[], rates: Rates): { rows: SaleRow[]; unconverted: number } {
  const out: SaleRow[] = [];
  let unconverted = 0;
  for (const r of rows) {
    const factor = hasPayoutRate(r) ? (r.payout_rate as number) : usdFactor(rates, saleDay(r), r.currency);
    if (factor === null) {
      unconverted += 1;
      continue;
    }
    out.push(r.currency === "USD" ? r : { ...r, price: round2(r.price * factor), currency: "USD" });
  }
  return { rows: out, unconverted };
}

type AdBatchLike = { id: string; product_id: string | null; meta?: { currency?: string } | null };

/** Días y monedas (que no son USD) para los que hace falta tipo de cambio. */
export function ratesNeeded(input: {
  sales: SaleRow[];
  batches: AdBatchLike[];
  creatives: { id: string; batch_id: string }[];
  spend: AdSpendRow[];
}): { days: string[]; currencies: string[] } {
  const days = new Set<string>();
  const currencies = new Set<string>();
  for (const s of input.sales) {
    if (s.currency === "USD" || hasPayoutRate(s)) continue;
    currencies.add(s.currency);
    const day = saleDay(s);
    if (day) days.add(day);
  }
  const batchCurrency = new Map(input.batches.map((b) => [b.id, b.meta?.currency ?? ""]));
  const creativeBatch = new Map(input.creatives.map((c) => [c.id, c.batch_id]));
  for (const r of input.spend) {
    const currency = batchCurrency.get(creativeBatch.get(r.creative_id) ?? "") ?? "";
    if (!currency || currency === "USD") continue;
    currencies.add(currency);
    days.add(r.day);
  }
  return { days: [...days].sort().reverse(), currencies: [...currencies].sort() };
}

/**
 * El gasto en anuncios en USD (tipo de cambio del día de cada gasto). Las campañas cuya moneda no
 * se conoce quedan como estaban y el cruce las excluye; las convertibles pasan a USD.
 */
export function adsToUsd(
  input: { batches: AdBatchLike[]; creatives: { id: string; batch_id: string }[]; spend: AdSpendRow[] },
  rates: Rates,
): { batches: AdBatchLike[]; spend: AdSpendRow[] } {
  const currencyOf = new Map(input.batches.map((b) => [b.id, b.meta?.currency ?? ""]));
  const creativeBatch = new Map(input.creatives.map((c) => [c.id, c.batch_id]));
  const spend: AdSpendRow[] = [];
  for (const r of input.spend) {
    const currency = currencyOf.get(creativeBatch.get(r.creative_id) ?? "") ?? "";
    if (!currency) {
      spend.push(r); // sin moneda: el cruce descarta la campaña entera
      continue;
    }
    const factor = usdFactor(rates, r.day, currency);
    if (factor !== null) spend.push({ ...r, spend: round2(Number(r.spend) * factor) });
  }
  const batches = input.batches.map((b) => {
    const currency = b.meta?.currency;
    return currency && usdFactor(rates, "", currency) !== null ? { ...b, meta: { ...b.meta, currency: "USD" } } : b;
  });
  return { batches, spend };
}

/** ¿El día `YYYY-MM-DD` cae entre `since` y `until` (ambos incluidos; vacío = sin límite)? */
export function inRange(day: string, since: string, until = ""): boolean {
  return (!since || day >= since) && (!until || day <= until);
}

export function summarize(rows: SaleRow[]): SalesSummary {
  const s = { paid: 0, refunded: 0, pending: 0, lost: 0, gross: 0, fees: 0, net: 0, netEstimated: 0, refundedAmount: 0 };
  for (const r of rows) {
    if (PAID.has(r.status)) {
      s.paid += 1;
      s.gross += r.price;
      s.fees += r.fee;
      if (typeof r.net_usd === "number") s.net += r.net_usd;
      else {
        s.net += r.price - r.fee;
        s.netEstimated += 1;
      }
    } else if (REFUNDED.has(r.status)) {
      s.refunded += 1;
      s.refundedAmount += r.price;
    } else if (PENDING.has(r.status)) s.pending += 1;
    else s.lost += 1;
  }
  const reached = s.paid + s.refunded;
  return {
    ...s,
    gross: round2(s.gross),
    fees: round2(s.fees),
    refundedAmount: round2(s.refundedAmount),
    net: round2(s.net),
    refundRate: reached ? round2((100 * s.refunded) / reached) : null,
    avgTicket: s.paid ? round2(s.gross / s.paid) : null,
  };
}

/** Monedas presentes, la de más ventas primero: nunca se suman monedas distintas. */
export function currenciesOf(rows: SaleRow[]): string[] {
  const count = new Map<string, number>();
  for (const r of rows) count.set(r.currency, (count.get(r.currency) ?? 0) + 1);
  return [...count.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c);
}

export function dailySales(rows: SaleRow[]): { day: string; gross: number; net: number; sales: number }[] {
  const days = new Map<string, { gross: number; net: number; sales: number }>();
  for (const r of rows) {
    if (!PAID.has(r.status)) continue;
    const day = saleDay(r);
    if (!day) continue;
    const d = days.get(day) ?? { gross: 0, net: 0, sales: 0 };
    d.gross += r.price;
    d.net += typeof r.net_usd === "number" ? r.net_usd : r.price - r.fee;
    d.sales += 1;
    days.set(day, d);
  }
  return [...days.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, v]) => ({ day, gross: round2(v.gross), net: round2(v.net), sales: v.sales }));
}

export type ProductSales = { productId: number | null; name: string; summary: SalesSummary };

export function byProduct(rows: SaleRow[]): ProductSales[] {
  const groups = new Map<string, SaleRow[]>();
  for (const r of rows) groups.set(String(r.product_id), [...(groups.get(String(r.product_id)) ?? []), r]);
  return [...groups.values()]
    .map((list) => ({
      productId: list[0].product_id,
      name: list.find((r) => r.product_name)?.product_name ?? String(list[0].product_id ?? "—"),
      summary: summarize(list),
    }))
    .sort((a, b) => b.summary.gross - a.summary.gross);
}

export type AdSpendRow = { creative_id: string; day: string; spend: number };

export type CrossRow = {
  productId: number;
  name: string;
  gross: number;
  net: number;
  spend: number;
  /** Ingresos brutos de Hotmart entre gasto en anuncios (ROAS real); nulo si no hubo gasto. */
  roas: number | null;
  /** Neto de Hotmart menos gasto en anuncios. */
  profit: number;
};

/**
 * Gasto en anuncios de los productos vinculados frente a lo que vendieron en Hotmart (misma moneda
 * y mismo período). Hotmart no dice qué anuncio originó cada venta: el cruce es por producto.
 * `excludedBatches` son las campañas cuya moneda no es la elegida o no se conoce.
 */
export function crossWithAds(input: {
  sales: SaleRow[];
  links: { hotmart_product_id: number; product_id: string }[];
  batches: { id: string; product_id: string | null; meta?: { currency?: string } | null }[];
  creatives: { id: string; batch_id: string }[];
  spend: AdSpendRow[];
  currency: string;
  since: string;
  /** Último día incluido; vacío = sin tope. */
  until?: string;
}): { rows: CrossRow[]; excludedBatches: number } {
  const linked = new Set(input.links.map((l) => l.product_id));
  const candidates = input.batches.filter((b) => b.product_id && linked.has(b.product_id));
  const usable = candidates.filter((b) => b.meta?.currency === input.currency);
  const batchOf = new Map(input.creatives.map((c) => [c.id, c.batch_id]));
  const productOfBatch = new Map(usable.map((b) => [b.id, b.product_id as string]));
  const spendByProduct = new Map<string, number>();
  for (const r of input.spend) {
    if (!inRange(r.day, input.since, input.until)) continue;
    const batch = batchOf.get(r.creative_id);
    const product = batch ? productOfBatch.get(batch) : undefined;
    if (product) spendByProduct.set(product, (spendByProduct.get(product) ?? 0) + Number(r.spend));
  }
  const sales = input.sales.filter((r) => r.currency === input.currency && inRange(saleDay(r), input.since, input.until));
  const rows = input.links
    .map((link) => {
      const summary = summarize(sales.filter((r) => r.product_id === link.hotmart_product_id));
      const spend = round2(spendByProduct.get(link.product_id) ?? 0);
      const name = sales.find((r) => r.product_id === link.hotmart_product_id)?.product_name ?? String(link.hotmart_product_id);
      return {
        productId: link.hotmart_product_id,
        name,
        gross: summary.gross,
        net: summary.net,
        spend,
        roas: spend ? round2(summary.gross / spend) : null,
        profit: round2(summary.net - spend),
      };
    })
    .filter((r) => r.spend > 0 || r.gross > 0)
    .sort((a, b) => b.profit - a.profit);
  return { rows, excludedBatches: candidates.length - usable.length };
}
