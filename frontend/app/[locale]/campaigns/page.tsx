import { setRequestLocale } from "next-intl/server";
import { CampaignsView } from "@/components/campaigns/campaigns-view";

export default async function CampaignsPage({ params }: PageProps<"/[locale]/campaigns">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <CampaignsView />;
}
