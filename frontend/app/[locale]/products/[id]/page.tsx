import { setRequestLocale } from "next-intl/server";
import { ProductView } from "@/components/product/product-view";

export default async function ProductPage({ params }: PageProps<"/[locale]/products/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <ProductView productId={id} />;
}
