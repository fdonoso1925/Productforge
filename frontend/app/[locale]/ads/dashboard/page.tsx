import { setRequestLocale } from "next-intl/server";
import { DashboardView } from "@/components/ads/dashboard-view";

export default async function AdDashboardPage({ params }: PageProps<"/[locale]/ads/dashboard">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <DashboardView />;
}
