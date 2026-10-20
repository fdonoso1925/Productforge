"use client";

import { useLocale, useTranslations } from "next-intl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { CommercialSheet, FileRow } from "@/lib/types";
import { DownloadButton } from "./product-view";

export function CommercialCard({ sheet, files }: { sheet: CommercialSheet; files: FileRow[] }) {
  const t = useTranslations("product.commercial");
  const locale = useLocale();
  const money = (value: number) =>
    new Intl.NumberFormat(locale === "pt" ? "pt-BR" : "es", { style: "currency", currency: sheet.currency }).format(
      value,
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{sheet.product_name}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 text-sm">
        <div className="flex flex-wrap gap-2">
          {files.map((f) => (
            <DownloadButton key={f.id} file={f} label={f.file_type.toUpperCase()} />
          ))}
        </div>
        <div>
          <p className="text-lg font-semibold leading-snug">{sheet.headline}</p>
          <p className="text-muted-foreground">{sheet.subheadline}</p>
        </div>
        <Row label={t("alternatives")}>{sheet.alternative_names.join(" · ")}</Row>
        <Row label={t("price")}>
          {money(sheet.main_price.min)} – {money(sheet.main_price.max)}
        </Row>
        <Row label={t("bumps")}>
          <ul className="flex flex-col gap-1">
            {sheet.order_bumps.map((b) => (
              <li key={b.title}>
                <b>{b.title}</b> · {money(b.price)} — <span className="text-muted-foreground">{b.checkout_text}</span>
              </li>
            ))}
          </ul>
        </Row>
        <Row label={t("bonuses")}>
          {sheet.bonuses.map((b) => `${b.title} (${money(b.perceived_value)})`).join(" · ")}
        </Row>
        <Row label={t("description")}>{sheet.short_description}</Row>
        <Row label={t("benefits")}>
          <ul className="list-disc pl-5">
            {sheet.benefit_bullets.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </Row>
        <Row label={t("hooks")}>
          <ol className="list-decimal pl-5">
            {sheet.ad_hooks.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ol>
        </Row>
      </CardContent>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[12rem_1fr]">
      <span className="font-medium text-muted-foreground">{label}</span>
      <div>{children}</div>
    </div>
  );
}
