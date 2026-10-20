import { setRequestLocale } from "next-intl/server";
import { Wizard } from "@/components/wizard/wizard";
import { createClient } from "@/lib/supabase/server";
import type { Niche } from "@/lib/types";

export default async function NewProductPage({ params }: PageProps<"/[locale]/new">) {
  const { locale } = await params;
  setRequestLocale(locale);
  const supabase = await createClient();
  // Lectura directa con RLS: el catálogo de nichos es visible para usuarios autenticados.
  const { data } = await supabase
    .from("niches")
    .select("id, slug, name, market")
    .eq("active", true)
    .order("sort_order");

  return <Wizard niches={(data ?? []) as Niche[]} defaultMarket={locale === "es" ? "es-LATAM" : "pt-BR"} />;
}
