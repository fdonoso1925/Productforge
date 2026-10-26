import { setRequestLocale } from "next-intl/server";
import { ProductView } from "@/components/product/product-view";

export default async function ProductPage({ params, searchParams }: PageProps<"/[locale]/products/[id]">) {
  const { locale, id } = await params;
  const { ads, page } = await searchParams;
  setRequestLocale(locale);
  // `?ads=1`: el usuario pidió, al crear el paquete, que le ofrezcamos los anuncios al terminar.
  return <ProductView productId={id} offerAds={ads === "1"} offerPage={page === "1"} />;
}
