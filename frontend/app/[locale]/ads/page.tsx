import { setRequestLocale } from "next-intl/server";
import { AdsList } from "@/components/ads/ads-list";

export default async function AdsPage({ params }: PageProps<"/[locale]/ads">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <AdsList />;
}
