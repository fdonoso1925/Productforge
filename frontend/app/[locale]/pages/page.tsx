import { setRequestLocale } from "next-intl/server";
import { PagesList } from "@/components/pages/pages-list";

export default async function PagesPage({ params }: PageProps<"/[locale]/pages">) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <PagesList />;
}
