import { ArrowRight, Megaphone, Plus } from "lucide-react";
import { getFormatter, getTranslations, setRequestLocale } from "next-intl/server";
import { Cover } from "@/components/library/cover";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Link } from "@/i18n/navigation";
import { createClient } from "@/lib/supabase/server";
import type { HistoryRow } from "@/lib/types";
import { BackendStatus } from "./backend-status";

type RecentRow = Pick<HistoryRow, "id" | "title" | "niche" | "market" | "main_format" | "status">;
const STATUSES = ["ready", "outline_ready", "generating", "error"] as const;
const MARKETS = ["es-LATAM", "pt-BR"] as const;
type Chip = { key: string; label: string; n: number; href: string; active: boolean };

export default async function HomePage({ params, searchParams }: PageProps<"/[locale]">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const { f, m } = await searchParams;
  const t = await getTranslations("home");
  const th = await getTranslations("history");
  const tf = await getTranslations("formats");
  const tm = await getTranslations("markets");
  const format = await getFormatter();
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = String(data?.claims?.email ?? "");
  // Saludo con nombre y apellido: «francisco.donoso.herrera@…» → «Francisco Donoso».
  const words = (email.split("@")[0] || email).split(/[._\-+\d]+/).filter(Boolean).slice(0, 2);
  const name = (words.length ? words : [email]).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");

  // Lecturas directas con RLS: solo se cuentan y suman cosas del propio usuario.
  const [products, batches, results, recent] = await Promise.all([
    supabase.from("products").select("id", { count: "exact", head: true }),
    supabase.from("ad_batches").select("id", { count: "exact", head: true }),
    supabase.from("ad_results").select("purchases, revenue").limit(5000),
    supabase
      .from("products")
      .select("id, title, niche, market, main_format, status")
      .order("created_at", { ascending: false })
      .limit(48),
  ]);
  const purchases = (results.data ?? []).reduce((a, r) => a + Number(r.purchases ?? 0), 0);
  const revenue = (results.data ?? []).reduce((a, r) => a + Number(r.revenue ?? 0), 0);
  const all = (recent.data ?? []) as RecentRow[];
  const number = (n: number) => format.number(n, { maximumFractionDigits: 0 });

  // Dos filtros que se combinan: idioma (mercado) y estado. Cada chip conserva el otro filtro.
  const market = MARKETS.find((x) => x === m);
  const filter = STATUSES.find((s) => s === f);
  const href = (status?: string, mk?: string) => {
    const q = new URLSearchParams();
    if (mk) q.set("m", mk);
    if (status) q.set("f", status);
    return q.size ? `/?${q}` : "/";
  };
  const inMarket = market ? all.filter((r) => r.market === market) : all;
  const rows = filter ? inMarket.filter((r) => r.status === filter) : inMarket;
  const counts = Object.fromEntries(STATUSES.map((s) => [s, inMarket.filter((r) => r.status === s).length]));
  const marketChips: Chip[] = [
    { key: "all", label: t("allLanguages"), n: all.length, href: href(filter), active: !market },
    ...MARKETS.map((mk) => ({
      key: mk,
      label: tm(mk),
      n: all.filter((r) => r.market === mk).length,
      href: href(filter, mk),
      active: market === mk,
    })),
  ];
  const chips: Chip[] = [
    { key: "all", label: t("filterAll"), n: inMarket.length, href: href(undefined, market), active: !filter },
    ...STATUSES.filter((s) => counts[s] > 0 || filter === s).map((s) => ({
      key: s,
      label: th(`status.${s}`),
      n: counts[s],
      href: href(s, market),
      active: filter === s,
    })),
  ];
  // «Continuar»: lo último que quedó a medias (sin generar, generando o con errores); si no, lo último.
  const pending = all.find((r) => r.status !== "ready") ?? all[0];
  const metrics = [
    { label: t("revenue"), value: revenue ? format.number(revenue, { minimumFractionDigits: 0, maximumFractionDigits: 2 }) : "—" },
    { label: t("products"), value: number(products.count ?? 0) },
    { label: t("ads"), value: number(batches.count ?? 0) },
    { label: t("purchases"), value: purchases ? number(purchases) : "—" },
  ];

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-6xl flex-1 flex-col gap-8 px-5 py-6 md:px-10 md:py-10">
      <section className="grid items-center gap-8 lg:grid-cols-[1fr_minmax(0,480px)]">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold tracking-[0.14em] text-lavender uppercase">
            {t("library", { count: products.count ?? 0 })}
          </p>
          <h1 className="mt-3 mb-3 text-[32px] leading-[1.1] font-semibold break-words md:text-[52px]">{name}</h1>
          <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground md:text-lg">{t("tagline")}</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/new" className={buttonVariants({ size: "lg" })}>
              <Plus aria-hidden />
              {t("newProduct")}
            </Link>
            <Link href="/ads/new" className={buttonVariants({ variant: "outline", size: "lg" })}>
              <Megaphone aria-hidden />
              {t("createAds")}
            </Link>
          </div>
        </div>

        {pending && (
          <div className="glass flex gap-5 rounded-[20px] p-4 md:p-5">
            <Cover seed={pending.id} title={pending.title ?? pending.niche} size="sm" className="w-24 shrink-0 md:w-28" />
            <div className="flex min-w-0 flex-1 flex-col justify-center gap-2.5">
              <p className="text-xs font-semibold tracking-[0.12em] text-lavender uppercase">{t("continueTitle")}</p>
              <p className="line-clamp-2 font-heading text-lg font-semibold md:text-xl">{pending.title ?? pending.niche}</p>
              <p className="truncate text-sm text-muted-foreground">
                {tf(`${pending.main_format}.name`)} · {tm(pending.market)}
              </p>
              <Progress value={pending.status === "ready" ? 100 : pending.status === "generating" ? 60 : 25} className="gap-0" />
              <Link href={`/products/${pending.id}`} className={buttonVariants({ size: "sm", className: "self-start" })}>
                {t("continueCta")}
                <ArrowRight aria-hidden />
              </Link>
            </div>
          </div>
        )}
      </section>

      <section aria-label={t("metrics")}>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {metrics.map((m) => (
            <div key={m.label} className="glass flex flex-col rounded-[18px] px-5 py-4">
              <dd className="order-1 font-heading text-2xl font-semibold md:text-[28px]">{m.value}</dd>
              <dt className="order-2 text-[13px] text-muted-foreground">{m.label}</dt>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="shelf" className="flex flex-col gap-5">
        {[
          { label: t("filterLanguage"), list: marketChips },
          { label: t("filters"), list: chips },
        ].map((group) => (
        <nav key={group.label} aria-label={group.label} className="-mx-5 flex gap-2.5 overflow-x-auto px-5 pb-1 md:mx-0 md:flex-wrap md:px-0">
          {group.list.map((c) => (
            <Link
              key={c.key}
              href={c.href}
              aria-current={c.active ? "true" : undefined}
              className={`flex h-10 shrink-0 items-center gap-2 rounded-full border px-4 text-sm font-medium transition-colors ${
                c.active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground hover:border-primary/70"
              }`}
            >
              {c.label}
              <span
                className={`rounded-[10px] px-[7px] py-0.5 text-xs ${c.active ? "bg-[#0b1026]/15" : "bg-accent text-accent-foreground"}`}
              >
                {c.n}
              </span>
            </Link>
          ))}
        </nav>
        ))}

        <div className="flex items-baseline justify-between">
          <h2 id="shelf" className="text-[22px] font-semibold md:text-[26px]">
            {t("title")}
          </h2>
          <span className="text-sm text-muted-foreground">{t("shown", { count: rows.length })}</span>
        </div>

        {rows.length === 0 ? (
          <p className="glass rounded-[20px] border-dashed p-10 text-center text-muted-foreground">
            {all.length === 0 ? t("empty") : t("noResults")}
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-3.5 md:grid-cols-3 md:gap-6 xl:grid-cols-4">
            {rows.map((row) => (
              <li
                key={row.id}
                className="glass group flex flex-col gap-3.5 rounded-[20px] p-2.5 transition-all duration-200 hover:-translate-y-1 hover:border-primary/45 hover:shadow-[0_18px_44px_rgb(3_5_20/0.5),0_0_32px_rgb(245_199_107/0.16)] md:p-3.5"
              >
                <Link href={`/products/${row.id}`} aria-label={row.title ?? row.niche} className="block">
                  <Cover seed={row.id} title={row.title ?? row.niche} className="transition-transform duration-500 group-hover:scale-[1.02]" />
                </Link>
                <div className="flex flex-col gap-1.5 px-1">
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="secondary" className="max-w-full truncate">
                      {tf(`${row.main_format}.name`)}
                    </Badge>
                    <Badge variant={row.status === "ready" ? "default" : row.status === "error" ? "destructive" : "outline"}>
                      {th(`status.${row.status}`)}
                    </Badge>
                  </div>
                  <p className="line-clamp-2 font-heading text-[15px] font-semibold md:text-base">{row.title ?? row.niche}</p>
                  <p className="truncate text-xs text-muted-foreground md:text-[13px]">{tm(row.market)}</p>
                </div>
                <div className="flex gap-2">
                  <Link href={`/products/${row.id}`} className={buttonVariants({ className: "h-10 flex-1" })}>
                    {t("view")}
                  </Link>
                  <Link
                    href={`/ads/new?product=${row.id}`}
                    aria-label={t("createAds")}
                    title={t("createAds")}
                    className={buttonVariants({ variant: "outline", size: "icon", className: "size-10 shrink-0" })}
                  >
                    <Megaphone aria-hidden />
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <BackendStatus
        labels={{
          checking: t("backendChecking"),
          ok: t("backendOk"),
          error: t.raw("backendError") as string,
        }}
      />
    </main>
  );
}
