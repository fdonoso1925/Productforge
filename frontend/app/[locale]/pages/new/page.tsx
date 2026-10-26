import { setRequestLocale } from "next-intl/server";
import { PageWizard } from "@/components/pages/page-wizard";

export default async function NewPagePage({ params, searchParams }: PageProps<"/[locale]/pages/new">) {
  const { locale } = await params;
  const { product } = await searchParams;
  setRequestLocale(locale);
  // `?product=<id>`: viene del paquete recién hecho.
  return <PageWizard productId={typeof product === "string" ? product : undefined} />;
}
