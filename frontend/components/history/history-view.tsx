"use client";

import { GitBranch } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/wizard/step-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Link } from "@/i18n/navigation";
import { dateRange, EMPTY_FILTERS, type HistoryFilters, hasFilters, sanitizeSearch } from "@/lib/filters";
import { FORMAT_ICONS } from "@/lib/formats";
import { createClient } from "@/lib/supabase/client";
import { FORMATS, type HistoryRow } from "@/lib/types";

const PAGE_SIZE = 20;
const COLUMNS = "id, title, niche, market, main_format, template_id, status, parent_product_id, created_at";
const DEBOUNCE_MS = 250;

type Result = { key: string } & ({ rows: HistoryRow[]; count: number } | { error: string });

// Lectura directa a Supabase: RLS garantiza que solo aparecen los paquetes del usuario.
async function query(filters: HistoryFilters, limit: number) {
  let request = createClient()
    .from("products")
    .select(COLUMNS, { count: "exact" })
    .order("created_at", { ascending: false })
    .range(0, limit - 1);
  if (filters.market) request = request.eq("market", filters.market);
  if (filters.format) request = request.eq("main_format", filters.format);
  if (filters.niche) request = request.eq("niche", filters.niche);
  const { gte, lt } = dateRange(filters.from, filters.to);
  if (gte) request = request.gte("created_at", gte);
  if (lt) request = request.lt("created_at", lt);
  const q = sanitizeSearch(filters.q);
  if (q) request = request.or(`title.ilike.%${q}%,niche.ilike.%${q}%`);
  const { data, count, error } = await request;
  if (error) throw new Error(error.message);
  return { rows: (data ?? []) as HistoryRow[], count: count ?? 0 };
}

export function HistoryView() {
  const t = useTranslations("history");
  const tApp = useTranslations("app");
  const tf = useTranslations("formats");
  const tm = useTranslations("markets");
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_FILTERS);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [result, setResult] = useState<Result | null>(null);
  const [niches, setNiches] = useState<string[]>([]);

  const set = (patch: Partial<HistoryFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE_SIZE);
  };

  // Nichos disponibles para el filtro (los que el usuario realmente usó).
  useEffect(() => {
    createClient()
      .from("products")
      .select("niche")
      .limit(500)
      .then(({ data }) => setNiches([...new Set((data ?? []).map((r) => r.niche as string))].sort()));
  }, []);

  // El resultado lleva la clave de la consulta que lo produjo: si no coincide con la actual,
  // la pantalla está cargando (sin setState sincrónico dentro del efecto).
  const key = JSON.stringify([filters, limit]);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      query(filters, limit).then(
        (r) => alive && setResult({ key, ...r }),
        (e) => alive && setResult({ key, error: e instanceof Error ? e.message : String(e) }),
      );
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` ya resume filters y limit
  }, [key]);

  const loading = result?.key !== key;
  const ready = result && "rows" in result ? result : null;

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          {tApp("name")}
        </Link>
      </header>

      <section aria-label={t("search")} className="grid gap-3 rounded-xl border bg-muted/30 p-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={t("search")} className="sm:col-span-2 lg:col-span-3">
          <Input
            type="search"
            maxLength={80}
            placeholder={t("searchPlaceholder")}
            value={filters.q}
            onChange={(e) => set({ q: e.target.value })}
          />
        </Field>
        <Field label={t("niche")}>
          <Select value={filters.niche} onChange={(niche) => set({ niche })} all={t("all")}>
            {niches.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("market")}>
          <Select value={filters.market} onChange={(market) => set({ market: market as HistoryFilters["market"] })} all={t("all")}>
            <option value="pt-BR">{tm("pt-BR")}</option>
            <option value="es-LATAM">{tm("es-LATAM")}</option>
          </Select>
        </Field>
        <Field label={t("format")}>
          <Select value={filters.format} onChange={(format) => set({ format: format as HistoryFilters["format"] })} all={t("all")}>
            {FORMATS.map((f) => (
              <option key={f} value={f}>
                {tf(`${f}.name`)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("from")}>
          <Input type="date" value={filters.from} max={filters.to || undefined} onChange={(e) => set({ from: e.target.value })} />
        </Field>
        <Field label={t("to")}>
          <Input type="date" value={filters.to} min={filters.from || undefined} onChange={(e) => set({ to: e.target.value })} />
        </Field>
        {hasFilters(filters) && (
          <div className="flex items-end">
            <Button variant="outline" onClick={() => set(EMPTY_FILTERS)}>
              {t("clear")}
            </Button>
          </div>
        )}
      </section>

      {result && "error" in result && result.error && <ErrorBox message={result.error} />}
      {loading && !ready && <Loading text="…" />}

      {ready && (
        <div className={`flex flex-col gap-3 transition-opacity ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {t("results", { count: ready.count })}
          </p>
          {ready.rows.length === 0 ? (
            <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
              {t("empty")}
              <Link
                href="/new"
                className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-foreground hover:bg-primary/80"
              >
                {t("emptyNew")}
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {ready.rows.map((row) => (
                <ProductItem key={row.id} row={row} />
              ))}
            </ul>
          )}
          {ready.rows.length < ready.count && (
            <Button variant="outline" className="self-center" onClick={() => setLimit((n) => n + PAGE_SIZE)}>
              {t("loadMore")}
            </Button>
          )}
        </div>
      )}
    </main>
  );
}

function ProductItem({ row }: { row: HistoryRow }) {
  const t = useTranslations("history");
  const tf = useTranslations("formats");
  const tm = useTranslations("markets");
  const locale = useLocale();
  const Icon = FORMAT_ICONS[row.main_format];
  const date = new Intl.DateTimeFormat(locale === "pt" ? "pt-BR" : "es", { dateStyle: "medium" }).format(
    new Date(row.created_at),
  );
  return (
    <li>
      <Link
        href={`/products/${row.id}`}
        className="flex min-w-0 flex-col gap-2 rounded-xl border p-4 transition-colors hover:bg-muted/60 sm:flex-row sm:items-center sm:justify-between"
      >
        <span className="flex min-w-0 flex-col gap-1">
          <span className="truncate font-medium">{row.title ?? row.niche}</span>
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{row.niche}</span>
            <span className="flex items-center gap-1">
              <Icon className="size-3.5" aria-hidden />
              {tf(`${row.main_format}.name`)}
            </span>
            <span>{row.template_id}</span>
            <span>{date}</span>
            {row.parent_product_id && (
              <span className="flex items-center gap-1">
                <GitBranch className="size-3.5" aria-hidden />
                {t("derived")}
              </span>
            )}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <Badge variant="secondary">{tm(row.market)}</Badge>
          <Badge variant={row.status === "ready" ? "default" : row.status === "error" ? "destructive" : "secondary"}>
            {t(`status.${row.status}`)}
          </Badge>
        </span>
      </Link>
    </li>
  );
}

function Field({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`flex flex-col gap-1.5 ${className ?? ""}`}>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function Select({
  value,
  onChange,
  all,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  all: string;
  children: React.ReactNode;
}) {
  return (
    <select
      className="h-8 rounded-lg border border-input bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{all}</option>
      {children}
    </select>
  );
}
