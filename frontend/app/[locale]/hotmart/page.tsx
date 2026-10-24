import { setRequestLocale } from "next-intl/server";
import { HotmartDashboard } from "@/components/hotmart/hotmart-dashboard";

export default async function HotmartPage({ params }: PageProps<"/[locale]/hotmart">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <HotmartDashboard />;
}
