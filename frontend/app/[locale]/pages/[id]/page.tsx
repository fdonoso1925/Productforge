import { setRequestLocale } from "next-intl/server";
import { PageView } from "@/components/pages/page-view";

export default async function PageDetailPage({ params }: PageProps<"/[locale]/pages/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <PageView pageId={id} />;
}
