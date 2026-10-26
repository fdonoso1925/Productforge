"use client";

import { FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

/**
 * Ofrece crear la página de ventas del paquete recién hecho.
 * `emphasis` = el usuario lo pidió al crear el paquete: se muestra como siguiente paso.
 */
export function PageOffer({ productId, emphasis }: { productId: string; emphasis: boolean }) {
  const t = useTranslations("product.page");
  return (
    <section
      className={`flex flex-wrap items-center justify-between gap-4 rounded-[20px] bg-card p-4 ${
        emphasis ? "border-primary bg-primary/5 ring-1 ring-primary/30" : "bg-muted/20"
      }`}
      aria-label={t("title")}
    >
      <div className="flex max-w-xl flex-col gap-1">
        <h2 className="flex items-center gap-2 font-semibold">
          <FileText className="size-4" aria-hidden />
          {emphasis ? t("titleNext") : t("title")}
        </h2>
        <p className="text-sm text-muted-foreground">{t("hint")}</p>
      </div>
      <Link
        href={`/pages/new?product=${productId}`}
        className={`inline-flex h-9 items-center gap-2 rounded-lg px-4 text-sm font-medium ${
          emphasis ? "bg-primary text-primary-foreground hover:bg-primary/80" : "border bg-background hover:bg-muted"
        }`}
      >
        {t("cta")}
      </Link>
    </section>
  );
}
