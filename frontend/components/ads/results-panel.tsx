"use client";

import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorBox } from "@/components/wizard/step-nav";
import {
  type CreativeGroup,
  derive,
  type ResultInput,
  type ResultRow,
  sumResults,
  validateResult,
} from "@/lib/ads";
import { ApiError, api } from "@/lib/api";

const SELECT_CLASS = "h-11 w-full min-w-0 rounded-[14px] border border-border bg-card px-3 text-sm font-semibold";

export function formatMetric(value: number | null, kind: "money" | "percent" | "ratio" | "int"): string {
  if (value === null) return "—";
  if (kind === "int") return value.toLocaleString();
  if (kind === "percent") return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} %`;
  if (kind === "ratio") return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}×`;
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Una fila de métricas totales (CTR, CPC, CPA y ROAS se calculan de los totales). */
export function MetricsLine({ rows }: { rows: Partial<ResultInput>[] }) {
  const t = useTranslations("ads.results");
  const total = sumResults(rows);
  const d = derive(total);
  const cells: [string, string][] = [
    [t("spend"), formatMetric(total.spend, "money")],
    [t("impressions"), formatMetric(total.impressions, "int")],
    [t("ctr"), formatMetric(d.ctr, "percent")],
    [t("purchases"), formatMetric(total.purchases, "int")],
    [t("cpa"), formatMetric(d.cpa, "money")],
    [t("roas"), formatMetric(d.roas, "ratio")],
  ];
  return (
    <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-sm sm:grid-cols-6">
      {cells.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

/** Resultados de un borrador (todos sus formatos): resumen, historial por día y carga a mano. */
export function ResultsPanel({
  group,
  results,
  onChanged,
}: {
  group: CreativeGroup;
  results: ResultRow[];
  onChanged: () => void;
}) {
  const t = useTranslations("ads.results");
  const tf = useTranslations("ads.wizard.formats");
  const [creativeId, setCreativeId] = useState(group.lead.id);
  const [form, setForm] = useState({ day: today(), spend: "", impressions: "", clicks: "", purchases: "", revenue: "" });
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const ids = useMemo(() => new Set(group.items.map((c) => c.id)), [group.items]);
  const mine = useMemo(
    () => results.filter((r) => ids.has(r.creative_id)).sort((a, b) => b.day.localeCompare(a.day)),
    [results, ids],
  );
  const ratioOf = (id: string) => group.items.find((c) => c.id === id)?.ratio ?? "";

  const input: ResultInput = {
    day: form.day,
    spend: Number(form.spend || 0),
    impressions: Number(form.impressions || 0),
    clicks: Number(form.clicks || 0),
    purchases: Number(form.purchases || 0),
    revenue: Number(form.revenue || 0),
  };
  const issues = validateResult(input);

  const save = async () => {
    setPending(true);
    setError(null);
    try {
      await api.adsSaveResult(creativeId, input);
      setForm({ ...form, spend: "", impressions: "", clicks: "", purchases: "", revenue: "" });
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? (e.errors.length ? e.errors.join(" · ") : e.message) : String(e));
    } finally {
      setPending(false);
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await api.adsDeleteResult(id);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const field = (key: keyof typeof form, label: string, step = "1") => (
    <div className="flex flex-col gap-1">
      <Label htmlFor={`r-${group.id}-${key}`}>{label}</Label>
      <Input
        id={`r-${group.id}-${key}`}
        type={key === "day" ? "date" : "number"}
        min={key === "day" ? undefined : 0}
        step={key === "day" ? undefined : step}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
    </div>
  );

  return (
    <section className="flex flex-col gap-4 rounded-xl border bg-muted/30 p-4" aria-label={t("title")}>
      <div>
        <h3 className="font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      {mine.length > 0 && <MetricsLine rows={mine} />}
      {mine.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {mine.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2">
              <span className="tabular-nums">
                {r.day} · {tf(ratioOf(r.creative_id) as "4x5")} · {formatMetric(r.spend, "money")} ·{" "}
                {formatMetric(r.impressions, "int")} {t("impressions").toLowerCase()} · {r.clicks} {t("clicks").toLowerCase()} ·{" "}
                {r.purchases} {t("purchases").toLowerCase()} · {t(`source.${r.source}`)}
              </span>
              <Button variant="ghost" size="icon-xs" onClick={() => remove(r.id)} aria-label={t("remove")}>
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor={`r-${group.id}-ratio`}>{t("format")}</Label>
          <select id={`r-${group.id}-ratio`} value={creativeId} onChange={(e) => setCreativeId(e.target.value)} className={SELECT_CLASS}>
            {group.items.map((c) => (
              <option key={c.id} value={c.id}>
                {tf(c.ratio)}
              </option>
            ))}
          </select>
        </div>
        {field("day", t("day"))}
        {field("spend", t("spend"), "0.01")}
        {field("impressions", t("impressions"))}
        {field("clicks", t("clicks"))}
        {field("purchases", t("purchases"))}
        {field("revenue", t("revenue"), "0.01")}
      </div>
      {issues.length > 0 && (form.spend || form.impressions || form.clicks) && (
        <ul className="list-disc rounded-lg bg-amber-500/10 p-3 pl-7 text-sm" aria-live="polite">
          {issues.map((i) => (
            <li key={i}>{t(`issues.${i}`)}</li>
          ))}
        </ul>
      )}
      {error && <ErrorBox message={error} />}
      <div className="flex justify-end">
        <Button onClick={save} disabled={pending || issues.length > 0 || input.impressions === 0}>
          {pending ? t("saving") : t("save")}
        </Button>
      </div>
    </section>
  );
}
