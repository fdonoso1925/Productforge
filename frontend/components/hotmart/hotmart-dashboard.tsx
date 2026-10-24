"use client";

import { RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatMetric } from "@/components/ads/results-panel";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { ApiError, api } from "@/lib/api";
import { byProduct, crossWithAds, currenciesOf, dailySales, type SaleRow, summarize } from "@/lib/hotmart";
import { createClient } from "@/lib/supabase/client";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";
const PERIODS = ["7", "30", "90", "all"] as const;
const STALE_MS = 30 * 60 * 1000; // al abrir, si la última lectura es más vieja, se actualiza sola

type Link = { hotmart_product_id: number; product_id: string };
type AppProduct = { id: string; niche: string; outline: { main?: { title?: string } } | null };
type AdBatch = { id: string; product_id: string | null; meta: { currency?: string } | null };
type Status = { configured: boolean; synced_at: string | null; last_error: string | null; count: number };
type Data = {
  sales: SaleRow[];
  links: Link[];
  products: AppProduct[];
  batches: AdBatch[];
  creatives: { id: string; batch_id: string }[];
  spend: { creative_id: string; day: string; spend: number }[];
};

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);
const productName = (p: AppProduct) => p.outline?.main?.title || p.niche;

/** Dashboard de Hotmart: ventas, ingresos, reembolsos y cruce con el gasto en Meta Ads. */
export function HotmartDashboard() {
  const t = useTranslations("hotmart");
  const r = useTranslations("ads.results");
  const tc = useTranslations("common");
  const [status, setStatus] = useState<Status | null>(null);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("30");
  const [currency, setCurrency] = useState("");

  const load = useCallback(async () => {
    const db = createClient();
    const [sales, links, products, batches, creatives, spend] = await Promise.all([
      db
        .from("hotmart_sales")
        .select("transaction, product_id, product_name, status, order_date, approved_date, price, currency, fee")
        .order("order_date", { ascending: false })
        .limit(20000),
      db.from("hotmart_product_links").select("hotmart_product_id, product_id"),
      db.from("products").select("id, niche, outline").order("created_at", { ascending: false }).limit(200),
      db.from("ad_batches").select("id, product_id, meta").limit(200),
      db.from("ad_creatives").select("id, batch_id").limit(5000),
      db.from("ad_results").select("creative_id, day, spend").limit(20000),
    ]);
    const failure = sales.error ?? links.error ?? products.error ?? batches.error ?? creatives.error ?? spend.error;
    if (failure) throw new Error(failure.message);
    setData({
      sales: (sales.data ?? []) as SaleRow[],
      links: (links.data ?? []) as Link[],
      products: (products.data ?? []) as AppProduct[],
      batches: (batches.data ?? []) as AdBatch[],
      creatives: (creatives.data ?? []) as Data["creatives"],
      spend: (spend.data ?? []) as Data["spend"],
    });
  }, []);

  const sync = useCallback(async () => {
    setSyncing(true);
    setError(null);
    try {
      await api.hotmartSync(90);
      setStatus(await api.hotmartStatus());
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setStatus(await api.hotmartStatus().catch(() => null));
    } finally {
      setSyncing(false);
    }
  }, [load]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const s = await api.hotmartStatus();
        if (!alive) return;
        setStatus(s);
        if (!s.configured) return;
        await load();
        const stale = !s.synced_at || Date.now() - new Date(s.synced_at).getTime() > STALE_MS;
        if (alive && s.configured && stale) await sync();
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [load, sync]);

  const since = period === "all" ? "" : daysAgo(Number(period) - 1);
  const view = useMemo(() => {
    if (!data) return null;
    const currencies = currenciesOf(data.sales);
    const active = currency && currencies.includes(currency) ? currency : (currencies[0] ?? "");
    const inPeriod = data.sales.filter(
      (s) => s.currency === active && (!since || (s.approved_date ?? s.order_date ?? "").slice(0, 10) >= since),
    );
    return {
      currencies,
      active,
      summary: summarize(inPeriod),
      series: dailySales(inPeriod),
      products: byProduct(inPeriod),
      cross: crossWithAds({ ...data, currency: active, since }),
    };
  }, [data, currency, since]);

  const linkOf = (hotmartId: number | null) => data?.links.find((l) => l.hotmart_product_id === hotmartId)?.product_id ?? "";

  const setLink = async (hotmartId: number, productId: string) => {
    setError(null);
    try {
      await api.hotmartLink(hotmartId, productId || null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const money = (v: number | null) => (v === null ? "—" : `${formatMetric(v, "money")} ${view?.active ?? ""}`);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        {status?.configured && (
          <div className="flex flex-col items-end gap-1">
            <Button variant="outline" size="sm" onClick={() => void sync()} disabled={syncing}>
              <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
              {syncing ? t("syncing") : t("refresh")}
            </Button>
            {status.synced_at && (
              <span className="text-xs text-muted-foreground">
                {t("syncedAt", { date: new Date(status.synced_at).toLocaleString() })}
              </span>
            )}
          </div>
        )}
      </header>

      {error && <ErrorBox message={error} />}
      {status?.last_error && !error && <p className="text-sm text-destructive">{status.last_error}</p>}
      {!status && !error && <Loading text={tc("loading")} />}
      {status && !status.configured && (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("notConfigured")}</p>
      )}

      {view && status?.configured && view.currencies.length === 0 && !syncing && (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("empty")}</p>
      )}

      {view && view.currencies.length > 0 && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="hm-period">{t("period")}</Label>
              <select id="hm-period" value={period} onChange={(e) => setPeriod(e.target.value as typeof period)} className={SELECT_CLASS}>
                {PERIODS.map((p) => (
                  <option key={p} value={p}>
                    {t(`periods.${p}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="hm-currency">{t("currency")}</Label>
              <select id="hm-currency" value={view.active} onChange={(e) => setCurrency(e.target.value)} className={SELECT_CLASS}>
                {view.currencies.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {(
              [
                [t("sales"), view.summary.paid.toLocaleString()],
                [t("gross"), money(view.summary.gross)],
                [t("net"), money(view.summary.net)],
                [t("avgTicket"), money(view.summary.avgTicket)],
                [t("refunds"), `${view.summary.refunded} · ${formatMetric(view.summary.refundRate, "percent")}`],
                [t("refundedAmount"), money(view.summary.refundedAmount)],
                [t("pending"), view.summary.pending.toLocaleString()],
                [t("lost"), view.summary.lost.toLocaleString()],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="rounded-[18px] bg-card p-4">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 text-xl font-bold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="-mt-3 text-xs text-muted-foreground">{t("netNote")}</p>

          <RevenueChart series={view.series} label={t("chart")} gross={t("gross")} net={t("net")} />

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold">{t("products")}</h2>
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[46rem] text-sm">
                <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="p-2 font-medium">{t("product")}</th>
                    <th className="p-2 text-right font-medium">{t("sales")}</th>
                    <th className="p-2 text-right font-medium">{t("gross")}</th>
                    <th className="p-2 text-right font-medium">{t("net")}</th>
                    <th className="p-2 text-right font-medium">{t("refunds")}</th>
                    <th className="p-2 font-medium">{t("linkedTo")}</th>
                  </tr>
                </thead>
                <tbody>
                  {view.products.map((p) => (
                    <tr key={String(p.productId)} className="border-t align-middle">
                      <td className="p-2 font-medium">{p.name}</td>
                      <td className="p-2 text-right tabular-nums">{p.summary.paid}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(p.summary.gross, "money")}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(p.summary.net, "money")}</td>
                      <td className="p-2 text-right tabular-nums">
                        {p.summary.refunded} · {formatMetric(p.summary.refundRate, "percent")}
                      </td>
                      <td className="p-2">
                        {p.productId !== null && (
                          <select
                            aria-label={t("linkedTo")}
                            value={linkOf(p.productId)}
                            onChange={(e) => void setLink(p.productId as number, e.target.value)}
                            className="h-9 w-full min-w-40 rounded-[12px] border border-border bg-card px-2 text-xs font-semibold"
                          >
                            <option value="">{t("notLinked")}</option>
                            {data?.products.map((app) => (
                              <option key={app.id} value={app.id}>
                                {productName(app)}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold">{t("cross.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("cross.hint")}</p>
            {view.cross.rows.length === 0 ? (
              <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("cross.empty")}</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border">
                <table className="w-full min-w-[40rem] text-sm">
                  <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="p-2 font-medium">{t("product")}</th>
                      <th className="p-2 text-right font-medium">{t("gross")}</th>
                      <th className="p-2 text-right font-medium">{t("net")}</th>
                      <th className="p-2 text-right font-medium">{t("cross.spend")}</th>
                      <th className="p-2 text-right font-medium">{r("roas")}</th>
                      <th className="p-2 text-right font-medium">{t("cross.profit")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.cross.rows.map((row) => (
                      <tr key={row.productId} className="border-t">
                        <td className="p-2 font-medium">{row.name}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(row.gross, "money")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(row.net, "money")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(row.spend, "money")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(row.roas, "ratio")}</td>
                        <td className={`p-2 text-right font-semibold tabular-nums ${row.profit < 0 ? "text-destructive" : ""}`}>
                          {formatMetric(row.profit, "money")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {view.cross.excludedBatches > 0 && (
              <p className="text-xs text-muted-foreground">{t("cross.excluded", { count: view.cross.excludedBatches, currency: view.active })}</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}

/** Barras de ingreso bruto y línea de neto por día (SVG propio). */
function RevenueChart({
  series,
  label,
  gross,
  net,
}: {
  series: { day: string; gross: number; net: number; sales: number }[];
  label: string;
  gross: string;
  net: string;
}) {
  if (series.length === 0) return null;
  const W = 640;
  const H = 180;
  const pad = { l: 8, r: 8, t: 12, b: 22 };
  const max = Math.max(1, ...series.map((d) => d.gross));
  const slot = (W - pad.l - pad.r) / series.length;
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const line = series.map((d, i) => `${pad.l + slot * i + slot / 2},${y(d.net)}`).join(" ");
  const first = series[0].day;
  const last = series[series.length - 1].day;
  return (
    <section className="flex flex-col gap-2 rounded-[18px] bg-card p-4" aria-label={label}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{label}</h2>
        <p className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-primary" aria-hidden />
            {gross}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 bg-foreground" aria-hidden />
            {net}
          </span>
        </p>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${first} – ${last}`} className="h-auto w-full">
        {series.map((d, i) => (
          <rect
            key={d.day}
            x={pad.l + slot * i + slot * 0.15}
            y={y(d.gross)}
            width={slot * 0.7}
            height={H - pad.b - y(d.gross)}
            rx={2}
            className="fill-primary"
          >
            <title>{`${d.day} · ${d.sales} · ${gross}: ${d.gross.toFixed(2)} · ${net}: ${d.net.toFixed(2)}`}</title>
          </rect>
        ))}
        <polyline points={line} fill="none" strokeWidth={2} strokeLinejoin="round" className="stroke-foreground" />
        <text x={pad.l} y={H - 6} className="fill-muted-foreground text-[11px]">
          {first}
        </text>
        <text x={W - pad.r} y={H - 6} textAnchor="end" className="fill-muted-foreground text-[11px]">
          {last}
        </text>
      </svg>
    </section>
  );
}
