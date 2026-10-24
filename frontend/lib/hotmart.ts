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
  fee: number;
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
  net: number;
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

export function summarize(rows: SaleRow[]): SalesSummary {
  const s = { paid: 0, refunded: 0, pending: 0, lost: 0, gross: 0, fees: 0, refundedAmount: 0 };
  for (const r of rows) {
    if (PAID.has(r.status)) {
      s.paid += 1;
      s.gross += r.price;
      s.fees += r.fee;
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
    net: round2(s.gross - s.fees),
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
    d.net += r.price - r.fee;
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
}): { rows: CrossRow[]; excludedBatches: number } {
  const linked = new Set(input.links.map((l) => l.product_id));
  const candidates = input.batches.filter((b) => b.product_id && linked.has(b.product_id));
  const usable = candidates.filter((b) => b.meta?.currency === input.currency);
  const batchOf = new Map(input.creatives.map((c) => [c.id, c.batch_id]));
  const productOfBatch = new Map(usable.map((b) => [b.id, b.product_id as string]));
  const spendByProduct = new Map<string, number>();
  for (const r of input.spend) {
    if (r.day < input.since) continue;
    const batch = batchOf.get(r.creative_id);
    const product = batch ? productOfBatch.get(batch) : undefined;
    if (product) spendByProduct.set(product, (spendByProduct.get(product) ?? 0) + Number(r.spend));
  }
  const sales = input.sales.filter((r) => r.currency === input.currency && saleDay(r) >= input.since);
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
