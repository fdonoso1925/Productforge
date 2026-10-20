"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";

export function LocaleSwitch() {
  const t = useTranslations("locale");
  const locale = useLocale();
  const pathname = usePathname();
  return (
    <Link
      href={pathname}
      locale={locale === "es" ? "pt" : "es"}
      className="text-sm text-muted-foreground underline-offset-4 hover:underline"
    >
      {t("switch")}
    </Link>
  );
}
