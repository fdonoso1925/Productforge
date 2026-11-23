"use client";

import { BarChart3, ChevronDown, ChevronRight, ExternalLink, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import { Fragment, useCallback, useEffect, useState } from "react";
import { formatMetric } from "@/components/ads/results-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import { ApiError, api } from "@/lib/api";
import {
  adsManagerUrl,
  CAMPAIGN_PRESETS,
  type Campaign,
  type CampaignDetail,
  type CampaignList,
  type CampaignPreset,
  known,
  KNOWN_OBJECTIVES,
  KNOWN_STATUSES,
  periodQuery,
  statusTone,
} from "@/lib/campaigns";

const SELECT = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

/** Todas las campañas de la cuenta de Meta con sus métricas (solo lectura, en vivo). */
export function CampaignsView() {
  const t = useTranslations("campaigns");
  const tc = useTranslations("common");
  const [preset, setPreset] = useState<CampaignPreset>("last_30d");
  const [from, setFrom] = useState(() => daysAgo(29));
  const [to, setTo] = useState(() => daysAgo(0));
  const [query, setQuery] = useState(() => periodQuery("last_30d", "", ""));
  const [data, setData] = useState<CampaignList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notConnected, setNotConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState<string | null>(null);

  const fetchList = useCallback(
    async (q: string, refresh: boolean) => {
      try {
        setData(await api.metaCampaigns(q, refresh));
        setNotConnected(false);
        setError(null);
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) setNotConnected(true);
        else setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // Cada período nuevo se lee al cambiar `query` (el «cargando» lo encienden los botones).
  useEffect(() => {
    let alive = true;
    api
      .metaCampaigns(query, false)
      .then((list) => {
        if (!alive) return;
        setData(list);
        setNotConnected(false);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 503) setNotConnected(true);
        else setError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [query]);

  const load = (refresh: boolean) => {
    setLoading(true);
    void fetchList(query, refresh);
  };

  const changeQuery = (next: string) => {
    if (next === query) return;
    setLoading(true);
    setOpenId(null);
    setQuery(next);
  };

  const pick = (value: CampaignPreset) => {
    setPreset(value);
    if (value !== "custom") changeQuery(periodQuery(value, "", ""));
  };

  const currency = data?.account.currency ?? "";
  const money = (v: number | null) => (v === null ? "—" : `${formatMetric(v, "money")} ${currency}`);
  const totals = data?.totals;

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-[26px] font-bold">
            <BarChart3 className="size-6" aria-hidden />
            {t("title")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("hint")}</p>
          {data && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("account", { name: data.account.name, currency: data.account.currency })} ·{" "}
              {t("fetchedAt", { date: new Date(data.fetched_at).toLocaleString() })}
            </p>
          )}
        </div>
        {!notConnected && (
          <Button variant="outline" size="sm" onClick={() => void load(true)} disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} aria-hidden />
            {t("refresh")}
          </Button>
        )}
      </header>

      {notConnected && (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">
          {t("notConnected")}{" "}
          <Link href="/settings" className="text-primary underline underline-offset-2">
            {t("connectLink")}
          </Link>
        </p>
      )}

      {!notConnected && (
        <section aria-label={t("period")} className="grid gap-3 sm:grid-cols-[minmax(0,16rem)_1fr] sm:items-end">
          <div className="flex flex-col gap-1">
            <Label htmlFor="cmp-period">{t("period")}</Label>
            <select id="cmp-period" value={preset} onChange={(e) => pick(e.target.value as CampaignPreset)} className={SELECT}>
              {CAMPAIGN_PRESETS.map((p) => (
                <option key={p} value={p}>
                  {t(`presets.${p}`)}
                </option>
              ))}
            </select>
          </div>
          {preset === "custom" && (
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="cmp-from">{t("from")}</Label>
                <Input id="cmp-from" type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="cmp-to">{t("to")}</Label>
                <Input id="cmp-to" type="date" value={to} min={from || undefined} max={daysAgo(0)} onChange={(e) => setTo(e.target.value)} />
              </div>
              <Button onClick={() => changeQuery(periodQuery("custom", from, to))} disabled={!from || !to || from > to || loading}>
                {t("apply")}
              </Button>
            </div>
          )}
        </section>
      )}

      {error && <ErrorBox message={error} />}
      {loading && !data && !notConnected && <Loading text={tc("loading")} />}

      {totals && data && (
        <>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {(
              [
                [t("metrics.spend"), money(totals.spend)],
                [t("metrics.impressions"), formatMetric(totals.impressions, "int")],
                [t("metrics.clicks"), formatMetric(totals.clicks, "int")],
                [t("metrics.ctr"), formatMetric(totals.ctr, "percent")],
                [t("metrics.cpc"), money(totals.cpc)],
                [t("metrics.checkouts"), formatMetric(totals.checkouts, "int")],
                [t("metrics.purchases"), formatMetric(totals.purchases, "int")],
                [t("metrics.cpa"), money(totals.cpa)],
                [t("metrics.revenue"), money(totals.revenue)],
                [t("metrics.roas"), formatMetric(totals.roas, "ratio")],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="glass rounded-[18px] p-4">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 text-xl font-bold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="-mt-3 text-xs text-muted-foreground">{t("note")}</p>

          {data.campaigns.length === 0 ? (
            <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("empty")}</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border">
              <table className="w-full min-w-[60rem] text-sm">
                <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="p-2 font-medium">{t("campaign")}</th>
                    <th className="p-2 font-medium">{t("status")}</th>
                    <th className="p-2 text-right font-medium">{t("budget")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.spend")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.impressions")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.clicks")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.ctr")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.cpc")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.purchases")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.cpa")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.roas")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.campaigns.map((c) => (
                    <Fragment key={c.id}>
                      <CampaignRow
                        campaign={c}
                        open={openId === c.id}
                        onToggle={() => setOpenId(openId === c.id ? null : c.id)}
                        money={money}
                      />
                      {openId === c.id && (
                        <tr className="border-t bg-white/[0.03]">
                          <td colSpan={11} className="p-3">
                            <CampaignPanel campaign={c} accountId={data.account.id} query={query} money={money} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}

function CampaignRow({
  campaign: c,
  open,
  onToggle,
  money,
}: {
  campaign: Campaign;
  open: boolean;
  onToggle: () => void;
  money: (v: number | null) => string;
}) {
  const t = useTranslations("campaigns");
  const m = c.metrics;
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <tr className="border-t align-middle hover:bg-white/[0.03]">
      <td className="p-2">
        <button type="button" onClick={onToggle} aria-expanded={open} className="flex items-start gap-1.5 text-left font-medium">
          <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {c.name}
            <span className="mt-0.5 flex flex-wrap gap-1.5 text-xs font-normal text-muted-foreground">
              {c.objective && <span>{known(KNOWN_OBJECTIVES, c.objective) ? t(`objectives.${c.objective}`) : c.objective}</span>}
              {c.from_app && <Badge variant="outline">{t("fromApp")}</Badge>}
            </span>
          </span>
        </button>
      </td>
      <td className="p-2">
        <Badge variant={statusTone(c.status)}>{known(KNOWN_STATUSES, c.status) ? t(`statuses.${c.status}`) : c.status}</Badge>
      </td>
      <td className="p-2 text-right tabular-nums">
        {c.budget ? `${money(c.budget.amount)}${c.budget.kind === "daily" ? t("perDay") : ""}` : t("adsetBudget")}
      </td>
      <td className="p-2 text-right font-semibold tabular-nums">{money(m.spend)}</td>
      <td className="p-2 text-right tabular-nums">{formatMetric(m.impressions, "int")}</td>
      <td className="p-2 text-right tabular-nums">{formatMetric(m.clicks, "int")}</td>
      <td className="p-2 text-right tabular-nums">{formatMetric(m.ctr, "percent")}</td>
      <td className="p-2 text-right tabular-nums">{money(m.cpc)}</td>
      <td className="p-2 text-right tabular-nums">{formatMetric(m.purchases, "int")}</td>
      <td className="p-2 text-right tabular-nums">{money(m.cpa)}</td>
      <td className="p-2 text-right tabular-nums">{formatMetric(m.roas, "ratio")}</td>
    </tr>
  );
}

/** Detalle de una campaña: gasto y clics por día, y sus anuncios. */
function CampaignPanel({
  campaign,
  accountId,
  query,
  money,
}: {
  campaign: Campaign;
  accountId: string;
  query: string;
  money: (v: number | null) => string;
}) {
  const t = useTranslations("campaigns");
  const tc = useTranslations("common");
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .metaCampaign(campaign.id, query)
      .then((d) => alive && setDetail(d))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [campaign.id, query]);

  const m = campaign.metrics;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>
          {t("metrics.reach")}: {formatMetric(m.reach, "int")} · {t("metrics.frequency")}: {formatMetric(m.frequency, "ratio")} ·{" "}
          {t("metrics.cpm")}: {money(m.cpm)} · {t("metrics.landingViews")}: {formatMetric(m.landing_views, "int")} ·{" "}
          {t("metrics.checkouts")}: {formatMetric(m.checkouts, "int")} · {t("metrics.revenue")}: {money(m.revenue)}
        </span>
        <a
          href={adsManagerUrl(accountId, campaign.id)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-primary underline underline-offset-2"
        >
          {t("openInAdsManager")}
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </div>
      {error && <ErrorBox message={error} />}
      {!detail && !error && <Loading text={tc("loading")} />}
      {detail && (
        <>
          <DailyChart days={detail.daily} label={t("daily")} spend={t("metrics.spend")} clicks={t("metrics.clicks")} empty={t("noDays")} />
          {detail.ads.length > 0 && (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full min-w-[44rem] text-xs">
                <thead className="bg-muted/40 text-left text-muted-foreground">
                  <tr>
                    <th className="p-2 font-medium">{t("ad")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.spend")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.impressions")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.clicks")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.ctr")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.purchases")}</th>
                    <th className="p-2 text-right font-medium">{t("metrics.cpa")}</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.ads.map((ad) => (
                    <tr key={ad.id} className="border-t">
                      <td className="p-2">
                        <span className="font-medium">{ad.name}</span>
                        {ad.adset && <span className="block text-muted-foreground">{ad.adset}</span>}
                      </td>
                      <td className="p-2 text-right tabular-nums">{money(ad.metrics.spend)}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(ad.metrics.impressions, "int")}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(ad.metrics.clicks, "int")}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(ad.metrics.ctr, "percent")}</td>
                      <td className="p-2 text-right tabular-nums">{formatMetric(ad.metrics.purchases, "int")}</td>
                      <td className="p-2 text-right tabular-nums">{money(ad.metrics.cpa)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Barras de gasto por día con la línea de clics (SVG propio). */
function DailyChart({
  days,
  label,
  spend,
  clicks,
  empty,
}: {
  days: CampaignDetail["daily"];
  label: string;
  spend: string;
  clicks: string;
  empty: string;
}) {
  if (days.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  const W = 640;
  const H = 160;
  const pad = { l: 8, r: 8, t: 10, b: 22 };
  const maxSpend = Math.max(1, ...days.map((d) => d.spend));
  const maxClicks = Math.max(1, ...days.map((d) => d.clicks));
  const slot = (W - pad.l - pad.r) / days.length;
  const y = (v: number, max: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const line = days.map((d, i) => `${pad.l + slot * i + slot / 2},${y(d.clicks, maxClicks)}`).join(" ");
  return (
    <figure className="flex flex-col gap-1" aria-label={label}>
      <figcaption className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">{label}</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-primary" aria-hidden />
          {spend}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-3 bg-foreground" aria-hidden />
          {clicks}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${days[0].day} – ${days[days.length - 1].day}`} className="h-auto w-full">
        {days.map((d, i) => (
          <rect
            key={d.day}
            x={pad.l + slot * i + slot * 0.15}
            y={y(d.spend, maxSpend)}
            width={slot * 0.7}
            height={H - pad.b - y(d.spend, maxSpend)}
            rx={2}
            className="fill-primary"
          >
            <title>{`${d.day} · ${spend}: ${d.spend.toFixed(2)} · ${clicks}: ${d.clicks}`}</title>
          </rect>
        ))}
        <polyline points={line} fill="none" strokeWidth={2} strokeLinejoin="round" className="stroke-foreground" />
        <text x={pad.l} y={H - 6} className="fill-muted-foreground text-[11px]">
          {days[0].day}
        </text>
        <text x={W - pad.r} y={H - 6} textAnchor="end" className="fill-muted-foreground text-[11px]">
          {days[days.length - 1].day}
        </text>
      </svg>
    </figure>
  );
}
