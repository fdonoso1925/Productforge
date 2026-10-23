import { setRequestLocale } from "next-intl/server";
import { InsightsView } from "@/components/ads/insights-view";

export default async function AdInsightsPage({ params }: PageProps<"/[locale]/ads/insights">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <InsightsView />;
}
