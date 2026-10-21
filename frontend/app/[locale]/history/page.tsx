import { setRequestLocale } from "next-intl/server";
import { HistoryView } from "@/components/history/history-view";

export default async function HistoryPage({ params }: PageProps<"/[locale]/history">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <HistoryView />;
}
