"use client";

import { Trophy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Link } from "@/i18n/navigation";
import type { InsightBlock, InsightItem, Insights } from "@/lib/ads";
import { ApiError, api } from "@/lib/api";
import type { Market } from "@/lib/types";
import { formatMetric } from "./results-panel";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

export function InsightsView() {
  const t = useTranslations("ads.insights");
  const tc = useTranslations("common");
  const tm = useTranslations("markets");
  const [market, setMarket] = useState<"" | Market>("");
  const [niche, setNiche] = useState("");
  const [debouncedNiche, setDebouncedNiche] = useState("");
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedNiche(niche.trim()), 400);
    return () => clearTimeout(timer);
  }, [niche]);

  useEffect(() => {
    let alive = true;
    api
      .adsInsights({ ...(market ? { market } : {}), ...(debouncedNiche ? { niche: debouncedNiche } : {}) })
      .then((result) => {
        if (!alive) return;
        setData(result);
        setError(null);
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [market, debouncedNiche]);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
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
          <Label htmlFor="ins-market">{t("market")}</Label>
          <select id="ins-market" value={market} onChange={(e) => setMarket(e.target.value as "" | Market)} className={SELECT_CLASS}>
            <option value="">{t("allMarkets")}</option>
            <option value="es-LATAM">{tm("es-LATAM")}</option>
            <option value="pt-BR">{tm("pt-BR")}</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="ins-niche">{t("niche")}</Label>
          <Input id="ins-niche" value={niche} onChange={(e) => setNiche(e.target.value)} placeholder={t("nichePlaceholder")} />
        </div>
      </div>

      {error && <ErrorBox message={error} />}
      {!data && !error && <Loading text={tc("loading")} />}
      {data && data.creatives_with_results === 0 && (
        <p className="rounded-lg border p-4 text-sm text-muted-foreground">{t("empty")}</p>
      )}
      {data && data.creatives_with_results > 0 && (
        <>
          <p className="text-sm text-muted-foreground">
            {t("summary", {
              count: data.creatives_with_results,
              spend: formatMetric(data.totals.spend, "money"),
              min: data.min_impressions.toLocaleString(),
            })}
          </p>
          {data.winner_angles.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-primary/5 p-4">
              <p className="text-sm">
                <strong>{t("winners")}:</strong>{" "}
                {data.winner_angles.map((a, i) => (
                  <span key={a}>
                    {i > 0 && " · "}
                    <AngleName id={a} />
                  </span>
                ))}
              </p>
              <Link
                href="/ads/new"
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/80"
              >
                {t("newBatch")}
              </Link>
            </div>
          )}
          <Section title={t("angles")} block={data.angles} label={(item) => <AngleName id={item.key} />} />
          <Section title={t("templates")} block={data.templates} label={(item) => <TemplateName id={item.key} />} />
          <Section
            title={t("hooks")}
            block={data.hooks}
            label={(item) => (
              <span className="flex flex-col">
                <span className="font-medium">{item.headline}</span>
                <span className="text-xs text-muted-foreground">
                  {item.angle && <AngleName id={item.angle} />} · {item.template_id && <TemplateName id={item.template_id} />}
                </span>
              </span>
            )}
          />
        </>
      )}
    </main>
  );
}

function AngleName({ id }: { id: string }) {
  const t = useTranslations("ads.angleNames");
  return <>{t.has(id) ? t(id) : id}</>;
}

function TemplateName({ id }: { id: string }) {
  const t = useTranslations("ads.templates");
  return <>{t.has(id) ? t(id) : id}</>;
}

function Section({
  title,
  block,
  label,
}: {
  title: string;
  block: InsightBlock;
  label: (item: InsightItem) => React.ReactNode;
}) {
  const t = useTranslations("ads.insights");
  const r = useTranslations("ads.results");
  if (block.items.length === 0) return null;
  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <span className="text-xs text-muted-foreground">{t(`metric.${block.metric}`)}</span>
      </div>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              <th className="p-2 font-medium">#</th>
              <th className="p-2 font-medium" />
              <th className="p-2 text-right font-medium">{r("spend")}</th>
              <th className="p-2 text-right font-medium">{r("impressions")}</th>
              <th className="p-2 text-right font-medium">{r("ctr")}</th>
              <th className="p-2 text-right font-medium">{r("purchases")}</th>
              <th className="p-2 text-right font-medium">{r("cpa")}</th>
              <th className="p-2 text-right font-medium">{r("roas")}</th>
            </tr>
          </thead>
          <tbody>
            {block.items.map((item) => (
              <tr key={item.key} className="border-t align-top">
                <td className="p-2 tabular-nums text-muted-foreground">{item.rank}</td>
                <td className="p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {label(item)}
                    {item.winner && (
                      <Badge variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                        <Trophy aria-hidden />
                        {t("winner")}
                      </Badge>
                    )}
                    {!item.enough_data && <Badge variant="outline">{t("fewData")}</Badge>}
                  </div>
                </td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.spend, "money")}</td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.impressions, "int")}</td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.ctr, "percent")}</td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.purchases, "int")}</td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.cpa, "money")}</td>
                <td className="p-2 text-right tabular-nums">{formatMetric(item.roas, "ratio")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
