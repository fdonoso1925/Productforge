import { Megaphone, Plus } from "lucide-react";
import { getFormatter, getTranslations, setRequestLocale } from "next-intl/server";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";
import { FORMAT_ICONS } from "@/lib/formats";
import { createClient } from "@/lib/supabase/server";
import type { HistoryRow } from "@/lib/types";
import { BackendStatus } from "./backend-status";

type RecentRow = Pick<HistoryRow, "id" | "title" | "niche" | "market" | "main_format" | "status">;

export default async function HomePage({ params }: PageProps<"/[locale]">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const th = await getTranslations("history");
  const tf = await getTranslations("formats");
  const tm = await getTranslations("markets");
  const format = await getFormatter();
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const email = String(data?.claims?.email ?? "");
  const name = email.split("@")[0] || email;

  // Lecturas directas con RLS: solo se cuentan y suman cosas del propio usuario.
  const [products, batches, results, recent] = await Promise.all([
    supabase.from("products").select("id", { count: "exact", head: true }),
    supabase.from("ad_batches").select("id", { count: "exact", head: true }),
    supabase.from("ad_results").select("purchases, revenue").limit(5000),
    supabase
      .from("products")
      .select("id, title, niche, market, main_format, status")
      .order("created_at", { ascending: false })
      .limit(6),
  ]);
  const purchases = (results.data ?? []).reduce((a, r) => a + Number(r.purchases ?? 0), 0);
  const revenue = (results.data ?? []).reduce((a, r) => a + Number(r.revenue ?? 0), 0);
  const rows = (recent.data ?? []) as RecentRow[];
  const number = (n: number) => format.number(n, { maximumFractionDigits: 0 });

  const metrics = [
    { label: t("products"), value: number(products.count ?? 0) },
    { label: t("ads"), value: number(batches.count ?? 0) },
    { label: t("purchases"), value: purchases ? number(purchases) : "—" },
  ];

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-3xl flex-1 flex-col gap-6 px-5 py-4 md:py-10">
      <header className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm text-muted-foreground">{t("greeting", { name })}</p>
          <h1 className="text-[26px] font-bold">{t("title")}</h1>
        </div>
        <div
          className="flex size-[42px] shrink-0 items-center justify-center rounded-full bg-border font-bold uppercase"
          aria-hidden
        >
          {name.charAt(0)}
        </div>
      </header>

      <section aria-label={t("metrics")} className="rounded-3xl bg-primary p-5 text-primary-foreground">
        <p className="text-[13px] font-semibold">{t("revenue")}</p>
        <p className="mt-0.5 text-[42px] leading-tight font-bold tracking-tight">
          {revenue
            ? format.number(revenue, { style: "decimal", minimumFractionDigits: 0, maximumFractionDigits: 2 })
            : "—"}
        </p>
        <dl className="mt-3.5 grid grid-cols-3 gap-2 border-t border-primary-foreground/20 pt-3.5">
          {metrics.map((m) => (
            <div key={m.label} className="flex flex-col">
              <dd className="order-1 text-xl font-bold">{m.value}</dd>
              <dt className="order-2 text-xs">{m.label}</dt>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="recent" className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 id="recent" className="text-[17px] font-bold">
            {t("recent")}
          </h2>
          <Link href="/new" className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Plus aria-hidden />
            {t("newShort")}
          </Link>
        </div>
        {rows.length === 0 ? (
          <p className="rounded-[20px] bg-card p-5 text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(270px,1fr))] gap-3">
            {rows.map((row) => {
              const Icon = FORMAT_ICONS[row.main_format];
              return (
                <li key={row.id} className="flex flex-col gap-3 rounded-[20px] bg-card p-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex size-11 shrink-0 items-center justify-center rounded-xl text-muted-foreground"
                      style={{ background: "repeating-linear-gradient(45deg,#1f1f23,#1f1f23 6px,#26262a 6px,#26262a 12px)" }}
                      aria-hidden
                    >
                      <Icon className="size-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15px] font-semibold">{row.title ?? row.niche}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {tf(`${row.main_format}.name`)} · {tm(row.market)}
                      </p>
                    </div>
                    <Badge variant={row.status === "ready" ? "default" : row.status === "error" ? "destructive" : "secondary"}>
                      {th(`status.${row.status}`)}
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Link
                      href={`/ads/new?product=${row.id}`}
                      className={buttonVariants({ variant: "outline", size: "sm", className: "flex-1" })}
                    >
                      <Megaphone aria-hidden />
                      {t("createAds")}
                    </Link>
                    <Link
                      href={`/products/${row.id}`}
                      className={buttonVariants({ variant: "outline", size: "sm", className: "flex-1" })}
                    >
                      {t("view")}
                    </Link>
                  </div>
                </li>
              );
            })}
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
