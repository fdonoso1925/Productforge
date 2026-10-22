import { setRequestLocale } from "next-intl/server";
import { AdsWizard, type ProductOption } from "@/components/ads/ads-wizard";
import { createClient } from "@/lib/supabase/server";

export default async function NewAdBatchPage({ params, searchParams }: PageProps<"/[locale]/ads/new">) {
  const { locale } = await params;
  const { product } = await searchParams;
  setRequestLocale(locale);
  const supabase = await createClient();
  // Lectura directa con RLS: solo los paquetes propios que ya tienen contenido.
  const { data } = await supabase
    .from("products")
    .select("id, title, niche, market, template_id")
    .in("status", ["ready", "error"])
    .order("created_at", { ascending: false })
    .limit(100);

  return (
    <AdsWizard
      products={(data ?? []) as ProductOption[]}
      initialProductId={typeof product === "string" ? product : undefined}
      defaultMarket={locale === "es" ? "es-LATAM" : "pt-BR"}
    />
  );
}
