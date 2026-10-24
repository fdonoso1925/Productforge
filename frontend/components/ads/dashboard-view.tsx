"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import {
  type BatchRow,
  dailySeries,
  derive,
  type ResultRow,
  summarizeCampaigns,
  sumResults,
} from "@/lib/ads";
import { createClient } from "@/lib/supabase/client";
import { formatMetric } from "./results-panel";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";
const PERIODS = ["7", "30", "90", "all"] as const;

type Batch = Pick<BatchRow, "id" | "niche" | "market" | "brief" | "meta" | "created_at">;
type Creative = { id: string; batch_id: string };
type Result = Pick<ResultRow, "creative_id" | "day" | "spend" | "impressions" | "clicks" | "purchases" | "revenue">;

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

/** Dashboard de campañas: totales, evolución diaria y una fila por campaña (lote de anuncios). */
export function DashboardView() {
  const t = useTranslations("ads.dashboard");
  const r = useTranslations("ads.results");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const [data, setData] = useState<{ batches: Batch[]; creatives: Creative[]; results: Result[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("30");
  const [market, setMarket] = useState("");

  useEffect(() => {
    let alive = true;
    const db = createClient();
    // Lectura directa con RLS: solo se ven los datos propios.
    void Promise.all([
      db.from("ad_batches").select("id, niche, market, brief, meta, created_at").order("created_at", { ascending: false }).limit(200),
      db.from("ad_creatives").select("id, batch_id").limit(5000),
      db.from("ad_results").select("creative_id, day, spend, impressions, clicks, purchases, revenue").limit(20000),
    ]).then(([b, c, res]) => {
      if (!alive) return;
      const failure = b.error ?? c.error ?? res.error;
      if (failure) setError(failure.message);
      else setData({ batches: (b.data ?? []) as Batch[], creatives: (c.data ?? []) as Creative[], results: (res.data ?? []) as Result[] });
    });
    return () => {
      alive = false;
    };
  }, []);

  const view = useMemo(() => {
    if (!data) return null;
    const allowed = new Set(data.batches.filter((b) => !market || b.market === market).map((b) => b.id));
    const creatives = data.creatives.filter((c) => allowed.has(c.batch_id));
    const ids = new Set(creatives.map((c) => c.id));
    const since = period === "all" ? "" : daysAgo(Number(period) - 1);
    const results = data.results.filter((x) => ids.has(x.creative_id) && x.day >= since);
    const totals = sumResults(results);
    return {
      totals,
      derived: derive(totals),
      series: dailySeries(results),
      campaigns: summarizeCampaigns(creatives, results),
    };
  }, [data, market, period]);

  const batchOf = (id: string) => data?.batches.find((b) => b.id === id);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-bold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
        </div>
        <Link href="/ads" className="text-sm text-muted-foreground hover:underline">
          {t("back")}
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="dash-period">{t("period")}</Label>
          <select id="dash-period" value={period} onChange={(e) => setPeriod(e.target.value as typeof period)} className={SELECT_CLASS}>
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {t(`periods.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="dash-market">{t("market")}</Label>
          <select id="dash-market" value={market} onChange={(e) => setMarket(e.target.value)} className={SELECT_CLASS}>
            <option value="">{t("allMarkets")}</option>
            <option value="es-LATAM">{tm("es-LATAM")}</option>
            <option value="pt-BR">{tm("pt-BR")}</option>
          </select>
        </div>
      </div>

      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading text={tc("loading")} />}
      {view && view.campaigns.length === 0 && (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("empty")}</p>
      )}
      {view && view.campaigns.length > 0 && (
        <>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {(
              [
                [r("spend"), formatMetric(view.totals.spend, "money")],
                [r("impressions"), formatMetric(view.totals.impressions, "int")],
                [r("ctr"), formatMetric(view.derived.ctr, "percent")],
                [r("purchases"), formatMetric(view.totals.purchases, "int")],
                [r("cpa"), formatMetric(view.derived.cpa, "money")],
                [r("roas"), formatMetric(view.derived.roas, "ratio")],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="rounded-[18px] bg-card p-4">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 text-xl font-bold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>

          <SpendChart series={view.series} label={t("chart")} spend={r("spend")} revenue={r("revenue")} />

          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold">{t("campaigns")}</h2>
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[46rem] text-sm">
                <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="p-2 font-medium">{t("campaign")}</th>
                    <th className="p-2 text-right font-medium">{r("spend")}</th>
                    <th className="p-2 text-right font-medium">{r("impressions")}</th>
                    <th className="p-2 text-right font-medium">{r("ctr")}</th>
                    <th className="p-2 text-right font-medium">{r("purchases")}</th>
                    <th className="p-2 text-right font-medium">{r("cpa")}</th>
                    <th className="p-2 text-right font-medium">{r("roas")}</th>
                  </tr>
                </thead>
                <tbody>
                  {view.campaigns.map((c) => {
                    const b = batchOf(c.batchId);
                    const active = Object.values(b?.meta?.statuses ?? {}).filter((s) => s === "ACTIVE").length;
                    return (
                      <tr key={c.batchId} className="border-t align-top">
                        <td className="p-2">
                          <Link href={`/ads/${c.batchId}`} className="font-medium hover:underline">
                            {b?.brief.product_name ?? c.batchId}
                          </Link>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <span>{b ? `${tm(b.market)} · ${b.niche}` : ""}</span>
                            {b?.meta?.status === "done" && <Badge variant="outline">{active > 0 ? t("live", { count: active }) : t("paused")}</Badge>}
                          </div>
                        </td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.totals.spend, "money")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.totals.impressions, "int")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.derived.ctr, "percent")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.totals.purchases, "int")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.derived.cpa, "money")}</td>
                        <td className="p-2 text-right tabular-nums">{formatMetric(c.derived.roas, "ratio")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

/** Barras de gasto y línea de ingresos por día (SVG propio, sin librerías). */
function SpendChart({
  series,
  label,
  spend,
  revenue,
}: {
  series: { day: string; spend: number; revenue: number }[];
  label: string;
  spend: string;
  revenue: string;
}) {
  if (series.length === 0) return null;
  const W = 640;
  const H = 180;
  const pad = { l: 8, r: 8, t: 12, b: 22 };
  const max = Math.max(1, ...series.flatMap((d) => [d.spend, d.revenue]));
  const slot = (W - pad.l - pad.r) / series.length;
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const line = series.map((d, i) => `${pad.l + slot * i + slot / 2},${y(d.revenue)}`).join(" ");
  const first = series[0].day;
  const last = series[series.length - 1].day;
  return (
    <section className="flex flex-col gap-2 rounded-[18px] bg-card p-4" aria-label={label}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{label}</h2>
        <p className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-primary" aria-hidden />
            {spend}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 bg-foreground" aria-hidden />
            {revenue}
          </span>
        </p>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${first} – ${last}`} className="h-auto w-full">
        {series.map((d, i) => (
          <rect
            key={d.day}
            x={pad.l + slot * i + slot * 0.15}
            y={y(d.spend)}
            width={slot * 0.7}
            height={H - pad.b - y(d.spend)}
            rx={2}
            className="fill-primary"
          >
            <title>{`${d.day} · ${spend}: ${d.spend.toFixed(2)} · ${revenue}: ${d.revenue.toFixed(2)}`}</title>
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
