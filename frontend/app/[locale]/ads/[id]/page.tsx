import { setRequestLocale } from "next-intl/server";
import { BatchView } from "@/components/ads/batch-view";

export default async function AdBatchPage({ params }: PageProps<"/[locale]/ads/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <BatchView batchId={id} />;
}
